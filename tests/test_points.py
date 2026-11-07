"""Test fitur poin loyalty: perhitungan, idempotency, routing event, pesan rusak, API, dan RBAC."""
import json
from types import SimpleNamespace

import pytest

from app.application.points_service import PointsService
from app.consumers.points_consumer import process_message
from app.infrastructure.database import create_session_factory, get_session_factory
from app.infrastructure.points_ledger import SqlAlchemyPointsLedger
from tests.conftest import auth, order
from tests.test_notification_consumer import FakeChannel

PAID = {"event_id": "evt-1", "type": "order.paid", "order_id": 1, "customer": "budi@mail.com", "total": 900_000}


@pytest.fixture
def service():
    return PointsService(SqlAlchemyPointsLedger(create_session_factory("sqlite://")))


def deliver(service, body, tag=1):
    channel = FakeChannel()
    result = process_message(channel, SimpleNamespace(delivery_tag=tag), body, service)
    return result, channel


def test_order_dibayar_menambah_poin(service):
    result, channel = deliver(service, json.dumps(PAID))
    assert result == "added"
    assert service.balance("budi@mail.com") == 90               # 900.000 / 10.000
    assert channel.acked == [1]


def test_event_dobel_tidak_menambah_poin_dua_kali(service):
    results = [deliver(service, json.dumps(PAID), tag=i)[0] for i in (1, 2, 3)]
    assert results == ["added", "skipped", "skipped"]
    assert service.balance("budi@mail.com") == 90


def test_poin_bertambah_dari_beberapa_order(service):
    deliver(service, json.dumps(PAID))
    deliver(service, json.dumps({**PAID, "event_id": "evt-2", "order_id": 2, "total": 250_000}))
    assert service.balance("budi@mail.com") == 115              # 90 + 25


def test_event_selain_order_paid_diabaikan(service):
    result, channel = deliver(service, json.dumps({**PAID, "type": "order.placed"}))
    assert result == "ignored"
    assert service.balance("budi@mail.com") == 0
    assert channel.acked == [1]


@pytest.mark.parametrize("body", [b"bukan json", json.dumps({"type": "order.paid"}),
                                  json.dumps({**PAID, "total": "sembilan ratus ribu"})])
def test_pesan_rusak_masuk_dlq(service, body):
    result, channel = deliver(service, body)
    assert result == "dead_lettered"
    assert channel.nacked == [(1, False)] and channel.acked == []


def test_api_saldo_poin(client):
    created = client.post("/orders", json=order((1, 2))).json()          # vip, total 900.000
    client.post(f"/orders/{created['id']}/pay")
    assert client.get("/customers/budi@mail.com/points").json() == {"customer": "budi@mail.com", "points": 0}

    ledger = SqlAlchemyPointsLedger(get_session_factory())
    PointsService(ledger).handle({**PAID, "order_id": created["id"]})   # yang biasanya dikerjakan consumer
    assert client.get("/customers/budi@mail.com/points").json()["points"] == 90


def test_api_poin_hanya_bisa_dilihat_pemilik_atau_admin(client):
    assert client.get("/customers/ani@mail.com/points").status_code == 403       # budi baca poin ani
    assert client.get("/customers/ani@mail.com/points",
                      headers=auth("admin@toko.com")).status_code == 200         # admin boleh
    client.headers.clear()
    assert client.get("/customers/budi@mail.com/points").status_code == 401      # belum login
