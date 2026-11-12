"""Test race condition di PostgreSQL sungguhan (SQLite tidak bisa: database-nya dikunci utuh saat menulis).

Test ini dilewati kalau TEST_POSTGRES_URL tidak di-set, jadi `pytest -q` biasa tetap cepat dan tanpa dependency.
Nama database wajib berakhiran _test, karena tabelnya dihapus dan dibuat ulang di setiap test.

    docker compose up -d postgres
    docker compose exec postgres createdb -U app orders_test
    TEST_POSTGRES_URL=postgresql+psycopg://app:app@localhost:5433/orders_test pytest tests/test_concurrency.py -v

Cara kerja: 8 thread (= 8 request bersamaan), masing-masing punya Unit of Work sendiri.
Langkah di domain sengaja dibuat lambat (sleep) tepat setelah data dibaca, supaya semua thread sempat membaca
nilai lama sebelum ada yang menulis. Tanpa row lock, hasilnya salah. Dengan row lock, request bergantian.
"""
import os
import threading
import time

import pytest
from sqlalchemy.engine import make_url

from app.application.order_service import OrderService
from app.application.points_service import PointsService
from app.domain.errors import OrderCannotBeChanged, OutOfStock, VoucherExhausted
from app.domain.money import Money
from app.domain.order import Order
from app.domain.product import Product
from app.domain.voucher import Voucher
from app.infrastructure.database import Base, create_session_factory
from app.infrastructure.points_ledger import SqlAlchemyPointsLedger
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import FakeEventPublisher, actor

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_POSTGRES_URL ke database PostgreSQL khusus test")

REQUESTS = 8
KEYBOARD = [{"product_id": 1, "qty": 1}]


@pytest.fixture
def factory():
    assert make_url(POSTGRES_URL).database.endswith("_test"), "nama database test harus berakhiran _test"
    factory = create_session_factory(POSTGRES_URL)
    engine = factory.kw["bind"]
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.products.add(Product("Keyboard", Money(500_000), 5))
        uow.vouchers.add(Voucher("HEMAT50", Money(50_000), 3))
        uow.commit()
    yield factory
    engine.dispose()


def slow(monkeypatch, cls, method):
    """Bikin method domain lambat, tepat setelah data dibaca dan sebelum ditulis."""
    original = getattr(cls, method)

    def slower(self, *args, **kwargs):
        time.sleep(0.05)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cls, method, slower)


def run_together(tasks):
    """Jalankan semua task di thread berbeda, mulai bersamaan. Hasil: nilai return atau exception-nya."""
    start = threading.Barrier(len(tasks))
    results = [None] * len(tasks)

    def worker(i, task):
        start.wait()
        try:
            results[i] = task()
        except Exception as exc:                              # noqa: BLE001  yang dicek tipenya nanti
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i, t)) for i, t in enumerate(tasks)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    return results


def service(factory) -> OrderService:
    return OrderService(SqlAlchemyUnitOfWork(factory), FakeEventPublisher())


def stock(factory) -> int:
    with SqlAlchemyUnitOfWork(factory) as uow:
        return uow.products.get(1).stock


def test_kuota_voucher_tidak_terpakai_lebih_dari_kuota(factory, monkeypatch):
    slow(monkeypatch, Voucher, "redeem")
    results = run_together([lambda i=i: service(factory).place_order(actor(f"u{i}@mail.com"), KEYBOARD, "HEMAT50")
                            for i in range(REQUESTS)])
    berhasil = [r for r in results if isinstance(r, Order)]
    ditolak = [r for r in results if isinstance(r, VoucherExhausted)]
    assert (len(berhasil), len(ditolak)) == (3, REQUESTS - 3)       # kuota 3 = tepat 3 order
    with SqlAlchemyUnitOfWork(factory) as uow:
        assert uow.vouchers.get("HEMAT50").quota == 0
    assert stock(factory) == 2                                      # order yang ditolak tidak mengurangi stok


def test_stok_tidak_terjual_lebih_dari_yang_ada(factory, monkeypatch):
    slow(monkeypatch, Product, "reserve")
    results = run_together([lambda i=i: service(factory).place_order(actor(f"u{i}@mail.com"), KEYBOARD)
                            for i in range(REQUESTS)])
    assert sum(isinstance(r, Order) for r in results) == 5          # stok 5 = tepat 5 order
    assert sum(isinstance(r, OutOfStock) for r in results) == REQUESTS - 5
    assert stock(factory) == 0


def test_bayar_dan_batal_bersamaan_hanya_satu_yang_menang(factory, monkeypatch):
    order = service(factory).place_order(actor("budi@mail.com"), KEYBOARD)
    admin = actor("admin@toko.com", role="admin")
    slow(monkeypatch, Order, "pay")
    slow(monkeypatch, Order, "cancel")
    results = run_together([lambda: service(factory).pay_order(order.id, admin),
                            lambda: service(factory).cancel_order(order.id, admin)])
    assert sum(isinstance(r, OrderCannotBeChanged) for r in results) == 1     # yang kalah ditolak
    with SqlAlchemyUnitOfWork(factory) as uow:
        status = uow.orders.get(order.id).status.value
    assert (status, stock(factory)) in {("paid", 4), ("cancelled", 5)}        # stok cocok dengan status akhir


def test_poin_customer_baru_dari_event_bersamaan_tidak_hilang(factory):
    points = PointsService(SqlAlchemyPointsLedger(factory))
    events = [{"event_id": f"evt-{i}", "type": "order.paid", "customer": "baru@mail.com", "total": 100_000}
              for i in range(REQUESTS)]
    results = run_together([lambda e=e: points.handle(e) for e in events])
    assert results == ["added"] * REQUESTS                           # tidak ada yang salah dianggap "skipped"
    assert points.balance("baru@mail.com") == REQUESTS * 10          # 100.000 / 10.000 = 10 poin per event


def test_event_yang_sama_bersamaan_hanya_dihitung_sekali(factory):
    points = PointsService(SqlAlchemyPointsLedger(factory))
    event = {"event_id": "evt-1", "type": "order.paid", "customer": "baru@mail.com", "total": 100_000}
    results = run_together([lambda: points.handle(event) for _ in range(REQUESTS)])
    assert sorted(results) == ["added"] + ["skipped"] * (REQUESTS - 1)
    assert points.balance("baru@mail.com") == 10
