"""Consumer: tambah poin loyalty dari event order.paid di queue "points".

Queue "points" di-bind ke exchange "orders" dengan routing key "order.paid",
jadi consumer ini hanya menerima event pembayaran. Consumer notifikasi tetap berjalan seperti biasa.
- Berhasil / sudah pernah diproses : ack
- Pesan rusak (InvalidEvent)       : nack(requeue=False) -> points.dlq
Database mati atau error lain: consumer berhenti tanpa ack, pesan tetap di queue dan diproses lagi
saat consumer dijalankan ulang.

Observability:
- Konteks trace dibaca dari header pesan (extract), tersambung ke trace API
- Setiap hasil dihitung di metric points_events_processed_total, dibuka di port POINTS_METRICS_PORT (8002)
- Log JSON terstruktur

Jalankan:
    python -m app.consumers.points_consumer
"""
import json
import logging

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind
from prometheus_client import start_http_server

from app.application.errors import InvalidEvent
from app.application.points_service import PointsService
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.logs import setup_logging
from app.infrastructure.metrics import POINT_EVENTS
from app.infrastructure.points_ledger import SqlAlchemyPointsLedger
from app.infrastructure.rabbitmq import POINTS_QUEUE, connect, declare_topology
from app.infrastructure.tracing import setup_tracing

logger = logging.getLogger("app.consumers.points")
tracer = trace.get_tracer("app.consumers.points")


def process_message(channel, method, body: bytes, service: PointsService, properties=None) -> str:
    headers = (properties.headers if properties and properties.headers else {})
    context = extract(headers)
    with tracer.start_as_current_span("process points", context=context, kind=SpanKind.CONSUMER):
        try:
            result = service.handle(json.loads(body))
            channel.basic_ack(method.delivery_tag)
        except (ValueError, InvalidEvent) as exc:                 # JSON rusak atau isi event salah
            logger.error("Pesan rusak, dipindah ke DLQ: %s", exc, extra={"error_type": "client"})
            channel.basic_nack(method.delivery_tag, requeue=False)
            result = "dead_lettered"
        POINT_EVENTS.labels(result).inc()
        logger.info("event poin diproses", extra={
            "event_id": getattr(properties, "message_id", None), "result": result})
        return result


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    setup_tracing("points-consumer")
    start_http_server(settings.points_metrics_port)         # http://localhost:8002/metrics
    service = PointsService(SqlAlchemyPointsLedger(get_session_factory()))

    with connect(settings.rabbitmq_url) as connection:
        channel = connection.channel()
        declare_topology(channel)
        channel.basic_qos(prefetch_count=1)
        logger.info("Menunggu event di queue %s ...", POINTS_QUEUE)
        for method, properties, body in channel.consume(POINTS_QUEUE):
            process_message(channel, method, body, service, properties)


if __name__ == "__main__":
    main()
