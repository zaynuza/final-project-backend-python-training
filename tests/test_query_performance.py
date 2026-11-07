"""Test optimasi query: jumlah query tetap, keyset pagination, dan index.

Jumlah query dihitung dengan event SQLAlchemy, jadi N+1 langsung ketahuan di test
walaupun database-nya SQLite di memory.
"""
import pytest
from sqlalchemy import event, inspect

from app.application.order_service import OrderService
from app.application.product_service import ProductService
from app.application.report_service import ReportService
from app.infrastructure.database import create_session_factory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.conftest import order
from tests.fakes import ADMIN, FakeCache, FakeEventPublisher, actor


@pytest.fixture
def session_factory():
    return create_session_factory("sqlite://")


@pytest.fixture
def queries(session_factory):
    executed = []
    event.listen(session_factory.kw["bind"], "before_cursor_execute",
                 lambda conn, cursor, statement, *args: executed.append(statement))
    return executed


def place_orders(session_factory, count: int, customer: str = "budi@mail.com") -> OrderService:
    ProductService(SqlAlchemyUnitOfWork(session_factory), FakeCache()).create_product("Keyboard", 500_000, 1000)
    service = OrderService(SqlAlchemyUnitOfWork(session_factory), FakeEventPublisher())
    for _ in range(count):
        service.place_order(actor(customer, "regular"), [{"product_id": 1, "qty": 1}])
    return service


@pytest.mark.parametrize("count", [5, 30])
def test_report_selalu_satu_query(session_factory, queries, count):
    place_orders(session_factory, count)
    queries.clear()
    report = ReportService(SqlAlchemyUnitOfWork(session_factory)).sales_summary()
    assert report["total_orders"] == count
    assert len(queries) == 1                       # tidak bertambah walaupun order makin banyak


def test_report_menghitung_diskon_dan_status(session_factory):
    ProductService(SqlAlchemyUnitOfWork(session_factory), FakeCache()).create_product("Keyboard", 500_000, 10)
    service = OrderService(SqlAlchemyUnitOfWork(session_factory), FakeEventPublisher())
    vip = service.place_order(actor("budi@mail.com", "vip"), [{"product_id": 1, "qty": 2}])      # diskon 10%
    service.pay_order(vip.id, ADMIN)
    cancelled = service.place_order(actor("ani@mail.com", "regular"), [{"product_id": 1, "qty": 1}])
    service.cancel_order(cancelled.id, ADMIN)
    service.place_order(actor("ani@mail.com", "regular"), [{"product_id": 1, "qty": 1}])          # pending

    report = ReportService(SqlAlchemyUnitOfWork(session_factory)).sales_summary()
    assert report == {"total_orders": 3, "paid_orders": 1, "cancelled_orders": 1, "revenue": 900_000}


def test_riwayat_order_tanpa_n_plus_1(session_factory, queries):
    service = place_orders(session_factory, 25)
    queries.clear()
    orders = service.list_orders(ADMIN, "budi@mail.com", limit=20)
    assert len(orders) == 20 and all(o.lines for o in orders)
    assert len(queries) == 2                       # order + semua item-nya (selectinload)


def test_keyset_pagination_tanpa_duplikat(session_factory):
    service = place_orders(session_factory, 25)
    place_orders(session_factory, 3, customer="ani@mail.com")

    first = service.list_orders(ADMIN, "budi@mail.com", limit=10)
    second = service.list_orders(ADMIN, "budi@mail.com", limit=10, after=first[-1].id)
    third = service.list_orders(ADMIN, "budi@mail.com", limit=10, after=second[-1].id)

    ids = [o.id for o in first + second + third]
    assert len(ids) == 25 and len(set(ids)) == 25
    assert ids == sorted(ids, reverse=True)        # terbaru dulu
    assert all(o.customer == "budi@mail.com" for o in first + second + third)


def test_index_sesuai_query(session_factory):
    inspector = inspect(session_factory.kw["bind"])
    order_indexes = [i["column_names"] for i in inspector.get_indexes("orders")]
    line_indexes = [i["column_names"] for i in inspector.get_indexes("order_lines")]
    assert ["customer", "id"] in order_indexes
    assert ["order_id"] in line_indexes


def test_api_riwayat_order(client):
    for _ in range(3):
        client.post("/orders", json=order((1, 1)))

    page = client.get("/orders", params={"customer": "budi@mail.com", "limit": 2}).json()
    assert [o["id"] for o in page["items"]] == [3, 2]
    assert page["next_after"] == 2

    last = client.get("/orders", params={"customer": "budi@mail.com", "limit": 2, "after": 2}).json()
    assert [o["id"] for o in last["items"]] == [1]
    assert last["next_after"] is None
