"""Unit test use case: pakai FakeUnitOfWork, tanpa FastAPI dan tanpa database."""
import pytest

from app.application.errors import OrderNotFound, ProductNotFound
from app.application.order_service import OrderService
from app.domain.errors import OrderCannotBeChanged, OutOfStock
from app.domain.money import Money
from app.domain.product import Product
from tests.fakes import ADMIN, FakeEventPublisher, FakeUnitOfWork, actor


def make_service():
    uow = FakeUnitOfWork([Product("Keyboard", Money(500_000), 5), Product("Mouse", Money(100_000), 1)])
    return OrderService(uow, FakeEventPublisher()), uow


def test_place_order_mengurangi_stok_dan_commit():
    service, uow = make_service()
    order = service.place_order(actor("budi@mail.com", "vip"), [{"product_id": 1, "qty": 2}])
    assert order.total == Money(900_000)
    assert uow.products.get(1).stock == 3
    assert uow.committed


def test_order_berhasil_mengumumkan_event_setelah_commit():
    service, uow = make_service()
    order = service.place_order(actor("budi@mail.com", "vip"), [{"product_id": 1, "qty": 2}])
    service.pay_order(order.id, ADMIN)

    placed, paid = service.events.published
    assert (placed["type"], paid["type"]) == ("order.placed", "order.paid")
    assert placed["order_id"] == order.id and placed["total"] == 900_000
    assert placed["event_id"] != paid["event_id"]          # setiap event punya id sendiri


def test_stok_kurang_tidak_commit_dan_tidak_ada_event():
    service, uow = make_service()
    with pytest.raises(OutOfStock):
        service.place_order(actor("budi@mail.com", "regular"), [{"product_id": 2, "qty": 3}])
    assert not uow.committed
    assert service.events.published == []


def test_cancel_mengembalikan_stok():
    service, uow = make_service()
    order = service.place_order(actor("budi@mail.com", "regular"), [{"product_id": 1, "qty": 2}])
    service.cancel_order(order.id, ADMIN)
    assert uow.products.get(1).stock == 5


def test_order_dibayar_tidak_bisa_dibatalkan():
    service, _ = make_service()
    order = service.place_order(actor("budi@mail.com", "regular"), [{"product_id": 1, "qty": 1}])
    service.pay_order(order.id, ADMIN)
    with pytest.raises(OrderCannotBeChanged):
        service.cancel_order(order.id, ADMIN)


def test_produk_dan_order_tidak_ditemukan():
    service, _ = make_service()
    with pytest.raises(ProductNotFound):
        service.place_order(actor("budi@mail.com", "regular"), [{"product_id": 99, "qty": 1}])
    with pytest.raises(OrderNotFound):
        service.get_order(99, ADMIN)
