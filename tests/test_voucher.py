"""Test fitur voucher: domain, use case (fake UoW), transaksi (SQLite di memory), dan API."""
import pytest

from app.application.errors import VoucherNotFound
from app.application.order_service import OrderService
from app.application.product_service import ProductService
from app.application.voucher_service import VoucherService
from app.domain.errors import OutOfStock, VoucherExhausted
from app.domain.money import Money
from app.domain.product import Product
from app.domain.voucher import Voucher
from app.infrastructure.database import create_session_factory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.conftest import auth
from tests.fakes import FakeCache, FakeEventPublisher, FakeUnitOfWork, actor

KEYBOARD = [{"product_id": 1, "qty": 1}]
BUDI = actor("budi@mail.com", "vip")


# ---------- domain ----------
def test_redeem_mengurangi_kuota_sampai_habis():
    voucher = Voucher("HEMAT50", Money(50_000), 1)
    voucher.redeem()
    assert voucher.quota == 0
    with pytest.raises(VoucherExhausted):
        voucher.redeem()


# ---------- use case (fake UoW) ----------
def make_service(quota=2):
    uow = FakeUnitOfWork([Product("Keyboard", Money(500_000), 5), Product("Mouse", Money(100_000), 1)],
                         [Voucher("HEMAT50", Money(50_000), quota)])
    return OrderService(uow, FakeEventPublisher()), uow


def test_voucher_menambah_diskon_dan_mengurangi_kuota():
    service, uow = make_service()
    order = service.place_order(BUDI, KEYBOARD, "HEMAT50")
    assert order.discount == Money(100_000)          # 10% vip (50.000) + voucher 50.000
    assert order.total == Money(400_000)
    assert uow.vouchers.get("HEMAT50").quota == 1


def test_potongan_voucher_tidak_membuat_total_negatif():
    service, uow = make_service()
    uow.vouchers.add(Voucher("GRATIS", Money(1_000_000), 1))
    order = service.place_order(actor("budi@mail.com", "regular"), [{"product_id": 2, "qty": 1}], "GRATIS")
    assert order.total == Money(0)


def test_voucher_tidak_ditemukan():
    service, _ = make_service()
    with pytest.raises(VoucherNotFound):
        service.place_order(actor("budi@mail.com", "regular"), KEYBOARD, "NGASAL")


def test_cancel_mengembalikan_kuota():
    service, uow = make_service()
    order = service.place_order(actor("budi@mail.com", "regular"), KEYBOARD, "HEMAT50")
    service.cancel_order(order.id, actor("budi@mail.com", "regular"))
    assert uow.vouchers.get("HEMAT50").quota == 2


# ---------- transaksi (SQLAlchemy sungguhan) ----------
def test_stok_kurang_kuota_voucher_tidak_terpakai():
    uow = SqlAlchemyUnitOfWork(create_session_factory("sqlite://"))
    ProductService(uow, FakeCache()).create_product("Keyboard", 500_000, 5)
    ProductService(uow, FakeCache()).create_product("Mouse", 100_000, 1)
    VoucherService(uow).create_voucher("HEMAT50", 50_000, 1)

    with pytest.raises(OutOfStock):
        OrderService(uow, FakeEventPublisher()).place_order(
            actor("budi@mail.com", "regular"), [{"product_id": 2, "qty": 3}], "HEMAT50")
    assert VoucherService(uow).get_voucher("HEMAT50").quota == 1


# ---------- API ----------
ADMIN_HEADERS = auth("admin@toko.com")


@pytest.fixture
def voucher_client(client):
    client.post("/vouchers", json={"code": "HEMAT50", "amount": 50_000, "quota": 1}, headers=ADMIN_HEADERS)
    return client


def order(voucher_code):
    return {"items": KEYBOARD, "voucher_code": voucher_code}


def test_api_order_dengan_voucher(voucher_client):
    created = voucher_client.post("/orders", json=order("HEMAT50"))
    assert created.status_code == 201
    assert (created.json()["total"], created.json()["voucher_code"]) == (400_000, "HEMAT50")
    assert voucher_client.get("/vouchers/HEMAT50", headers=ADMIN_HEADERS).json()["quota"] == 0


def test_api_error_voucher(voucher_client):
    voucher_client.post("/orders", json=order("HEMAT50"))
    habis = voucher_client.post("/orders", json=order("HEMAT50"))
    assert habis.status_code == 409
    assert habis.json()["error"]["code"] == "voucher_exhausted"

    tidak_ada = voucher_client.post("/orders", json=order("NGASAL"))
    assert tidak_ada.status_code == 404
    assert tidak_ada.json()["error"]["code"] == "voucher_not_found"

    dobel = voucher_client.post("/vouchers", json={"code": "HEMAT50", "amount": 10_000, "quota": 1},
                                headers=ADMIN_HEADERS)
    assert dobel.status_code == 409
    assert dobel.json()["error"]["code"] == "voucher_already_exists"


def test_api_voucher_hanya_untuk_admin(voucher_client):
    assert voucher_client.get("/vouchers/HEMAT50").status_code == 403      # budi (customer)
    assert voucher_client.post("/vouchers", json={"code": "BARU10", "amount": 10_000, "quota": 1}).status_code == 403
    voucher_client.headers.clear()
    assert voucher_client.get("/vouchers/HEMAT50").status_code == 401      # belum login
