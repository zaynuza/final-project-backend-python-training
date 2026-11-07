"""Test observability: request_id, log JSON, metrics, health check, klasifikasi error, dan trace di pesan."""
import json
import logging

from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_health_checks, get_product_service
from app.infrastructure.logs import JsonFormatter, RequestContextFilter, request_id_var
from app.infrastructure.rabbitmq import message_properties
from app.main import app


def test_request_id_dibuat_jika_belum_ada(client):
    response = client.get("/products")
    assert len(response.headers["X-Request-ID"]) == 32


def test_request_id_dari_client_dipakai_ulang(client):
    response = client.get("/products", headers={"X-Request-ID": "req-123"})
    assert response.headers["X-Request-ID"] == "req-123"


def test_log_json_berisi_request_id_dan_field_extra():
    record = logging.makeLogRecord({"name": "app", "levelname": "INFO", "msg": "order dibuat",
                                    "order_id": 7})
    request_id_var.set("req-123")
    RequestContextFilter().filter(record)
    log = json.loads(JsonFormatter().format(record))
    assert log["message"] == "order dibuat"
    assert log["order_id"] == 7
    assert log["request_id"] == "req-123"


def test_access_log_mencatat_route_dan_status(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/orders/99")
    record = caplog.records[-1]
    assert (record.route, record.status) == ("/orders/{order_id}", 404)


def test_metrics_menghitung_request_per_route(client):
    client.get("/orders/99")
    text = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/orders/{order_id}",status="404"}' in text
    assert "http_request_duration_seconds_bucket" in text


def test_readiness_ok_jika_semua_dependency_hidup(client):
    app.dependency_overrides[get_health_checks] = lambda: {"database": lambda: None, "redis": lambda: None}
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


def test_readiness_503_jika_dependency_mati(client):
    def redis_down():
        raise ConnectionError("Redis mati")

    app.dependency_overrides[get_health_checks] = lambda: {"database": lambda: None, "redis": redis_down}
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "down: ConnectionError"
    assert client.get("/health/live").status_code == 200       # liveness tidak ikut gagal


def test_error_client_dicatat_warning(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.errors"):
        response = client.get("/orders/99")
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert caplog.records[-1].levelname == "WARNING"
    assert caplog.records[-1].error_type == "client"


def test_database_mati_jadi_503_dependency(client, caplog):
    def database_down():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_product_service] = database_down
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = client.get("/products")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert caplog.records[-1].error_type == "dependency"


def test_bug_jadi_500_dengan_traceback_di_log(caplog):
    from fastapi.testclient import TestClient

    def broken():
        raise ZeroDivisionError("division by zero")

    app.dependency_overrides[get_product_service] = broken
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = TestClient(app, raise_server_exceptions=False).get("/products")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert caplog.records[-1].error_type == "bug"
    assert caplog.records[-1].exc_info is not None


def test_konteks_trace_ikut_di_header_pesan():
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("POST /orders") as span:
        properties = message_properties({"event_id": "evt-1", "type": "order.placed"})
    trace_id = f"{span.get_span_context().trace_id:032x}"
    assert trace_id in properties.headers["traceparent"]
