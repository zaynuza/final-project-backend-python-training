"""Consumer: kirim notifikasi dari event order di queue "notifications".

Consumer adalah titik masuk seperti route di api/ dan task di worker/:
menerima pesan, memanggil use case (NotificationService), lalu memutuskan ack/nack.
- Berhasil / sudah pernah dikirim   : ack
- Pesan rusak (InvalidEvent)        : nack(requeue=False) -> langsung ke DLQ, tidak di-retry
- Server notifikasi gangguan        : retry dengan jeda (1 s, 2 s, 4 s), lewat batas -> DLQ
Ack dikirim setelah proses selesai, jadi consumer crash = pesan dikirim ulang, bukan hilang.

Observability:
- Konteks trace dibaca dari header pesan (extract), jadi span consumer masuk ke trace request API
- Setiap hasil dihitung di metric notifications_processed_total, dibuka di port CONSUMER_METRICS_PORT
- Log JSON membawa event_id dan trace_id

Jalankan dari folder starter/:
    python -m app.consumers.notification_consumer
"""
import json
import logging

import pika
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind
from prometheus_client import start_http_server

from app.application.errors import InvalidEvent
from app.application.notification_service import NotificationService
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.logs import setup_logging
from app.infrastructure.metrics import NOTIFICATIONS
from app.infrastructure.notification_log import SqlAlchemyNotificationLog
from app.infrastructure.notifiers import NotificationServiceDown, create_notifier
from app.infrastructure.rabbitmq import QUEUE, RETRY_QUEUE, connect, declare_topology
from app.infrastructure.tracing import setup_tracing

logger = logging.getLogger("app.consumers.notification")
tracer = trace.get_tracer("app.consumers.notification")


def process_message(channel, method, properties, body: bytes, service: NotificationService,
                    max_retries: int, retry_delay_ms: int) -> str:
    headers = properties.headers or {}
    context = extract(headers)                               # sambung ke trace API yang mengirim event
    with tracer.start_as_current_span("process notification", context=context, kind=SpanKind.CONSUMER):
        result = handle(channel, method, properties, body, service, max_retries, retry_delay_ms)
        NOTIFICATIONS.labels(result).inc()
        logger.info("event diproses", extra={"event_id": properties.message_id, "result": result})
    return result


def handle(channel, method, properties, body: bytes, service: NotificationService,
           max_retries: int, retry_delay_ms: int) -> str:
    headers = properties.headers or {}
    retries = headers.get("x-retries", 0)
    try:
        result = service.handle(json.loads(body))
        channel.basic_ack(method.delivery_tag)
        return result
    except (ValueError, InvalidEvent) as exc:                 # JSON rusak atau isi event salah
        logger.error("pesan rusak, dipindah ke DLQ: %s", exc, extra={"error_type": "client"})
        channel.basic_nack(method.delivery_tag, requeue=False)
        return "dead_lettered"
    except NotificationServiceDown as exc:
        if retries >= max_retries:
            logger.error("[ALERT] gagal %s kali, dipindah ke DLQ: %s", retries + 1, exc,
                         extra={"error_type": "dependency"})
            channel.basic_nack(method.delivery_tag, requeue=False)
            return "dead_lettered"
        delay_ms = retry_delay_ms * 2 ** retries
        channel.basic_publish("", RETRY_QUEUE, body, pika.BasicProperties(
            content_type="application/json", message_id=properties.message_id,
            headers={**headers, "x-retries": retries + 1},   # traceparent ikut dibawa
            expiration=str(delay_ms), delivery_mode=pika.DeliveryMode.Persistent))
        channel.basic_ack(method.delivery_tag)
        logger.warning("%s, retry ke-%s dalam %s ms", exc, retries + 1, delay_ms,
                       extra={"error_type": "dependency"})
        return "retrying"


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    setup_tracing("notification-consumer")
    start_http_server(settings.consumer_metrics_port)        # http://localhost:8001/metrics
    service = NotificationService(
        create_notifier(settings.notification_channel, settings.notification_fail_rate),
        SqlAlchemyNotificationLog(get_session_factory()))

    with connect(settings.rabbitmq_url) as connection:
        channel = connection.channel()
        declare_topology(channel)
        channel.basic_qos(prefetch_count=1)                   # pegang 1 pesan yang belum di-ack
        logger.info("menunggu event di queue %s", QUEUE)
        for method, properties, body in channel.consume(QUEUE):
            process_message(channel, method, properties, body, service,
                            settings.notification_max_retries, settings.notification_retry_delay_ms)


if __name__ == "__main__":
    main()
