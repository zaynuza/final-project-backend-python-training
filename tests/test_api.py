"""Test API: Celery berjalan eager, jadi report langsung dikerjakan di dalam test.
Event yang diumumkan API ditangkap FakeEventPublisher (fixture events).

Fixture client dan helper order ada di conftest.py.
"""
from tests.conftest import auth, order


def test_buat_order_mengurangi_stok_dan_mengumumkan_event(client, events):
    created = client.post("/orders", json=order((1, 2)))
    assert created.status_code == 201
    assert created.json()["total"] == 900_000
    assert client.get("/products/1").json()["stock"] == 3
    assert [(e["type"], e["order_id"], e["total"]) for e in events.published] == [("order.placed", 1, 900_000)]


def test_stok_kurang_semua_dibatalkan_tanpa_event(client, events):
    response = client.post("/orders", json=order((1, 2), (2, 3)))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "out_of_stock"
    assert client.get("/products/1").json()["stock"] == 5
    assert events.published == []


def test_cancel_mengembalikan_stok_lalu_bayar_ditolak(client):
    order_id = client.post("/orders", json=order((1, 2))).json()["id"]
    assert client.post(f"/orders/{order_id}/cancel").json()["status"] == "cancelled"
    assert client.get("/products/1").json()["stock"] == 5
    assert client.post(f"/orders/{order_id}/pay").json()["error"]["code"] == "order_cannot_be_changed"


def test_report_penjualan_lewat_background_job(client):
    paid = client.post("/orders", json=order((1, 2))).json()["id"]
    client.post(f"/orders/{paid}/pay")
    cancelled = client.post("/orders", json=order((2, 1))).json()["id"]
    client.post(f"/orders/{cancelled}/cancel")

    job = client.post("/reports/sales", headers=auth("admin@toko.com"))
    assert job.status_code == 202

    status = client.get(job.json()["status_url"], headers=auth("admin@toko.com")).json()
    assert status["status"] == "done"
    assert status["result"] == {"total_orders": 2, "paid_orders": 1, "cancelled_orders": 1, "revenue": 900_000}


def test_format_error_konsisten(client):
    not_found = client.get("/orders/99")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "order_not_found"

    invalid = client.post("/orders", json={"customer": "budi@mail.com", "items": []})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_middleware_menambah_header(client):
    assert "x-process-time" in client.get("/products").headers
