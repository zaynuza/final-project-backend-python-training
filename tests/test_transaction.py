"""Test transaksi dengan SQLAlchemy sungguhan (SQLite di memory).

Membuktikan rollback benar-benar terjadi di database, bukan cuma di fake.
"""
import pytest

from app.application.order_service import OrderService
from app.application.product_service import ProductService
from app.domain.errors import OutOfStock
from app.infrastructure.database import create_session_factory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.fakes import ADMIN, FakeCache, FakeEventPublisher, actor


@pytest.fixture
def uow():
    uow = SqlAlchemyUnitOfWork(create_session_factory("sqlite://"))
    products = ProductService(uow, FakeCache())
    products.create_product("Keyboard", 500_000, 5)
    products.create_product("Mouse", 100_000, 1)
    return uow


def test_satu_item_gagal_semua_dibatalkan(uow):
    service = OrderService(uow, FakeEventPublisher())
    with pytest.raises(OutOfStock):
        service.place_order(actor("budi@mail.com", "regular"),
                            [{"product_id": 1, "qty": 2}, {"product_id": 2, "qty": 3}])

    stocks = [p.stock for p in ProductService(uow, FakeCache()).list_products()]
    assert stocks == [5, 1]                        # stok Keyboard tidak ikut berkurang
    with uow:
        assert uow.orders.get(1) is None           # order tidak tersimpan


def test_order_berhasil_tersimpan_lengkap(uow):
    service = OrderService(uow, FakeEventPublisher())
    order = service.place_order(actor("budi@mail.com", "member"),
                                [{"product_id": 1, "qty": 2}, {"product_id": 2, "qty": 1}])

    saved = service.get_order(order.id, ADMIN)
    assert [line.product for line in saved.lines] == ["Keyboard", "Mouse"]
    assert saved.total == order.total
    assert [p.stock for p in ProductService(uow, FakeCache()).list_products()] == [3, 0]
