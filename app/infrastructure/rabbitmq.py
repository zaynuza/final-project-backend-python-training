"""Infrastructure: RabbitMQ (topologi + adapter port EventPublisher).

Topologi:
    exchange "orders" (topic) --order.*--> notifications
    notifications        --nack(requeue=False)-->  notifications.dlq
    notifications.retry  --setelah expiration--->  notifications (dicoba lagi)

declare_topology dipanggil oleh publisher dan consumer. Deklarasi bersifat idempotent,
jadi urutan menjalankan API dan consumer tidak penting, dan event tidak hilang karena queue belum ada.

Tracing: konteks trace (traceparent) ikut dikirim di header pesan lewat inject(),
supaya span consumer tersambung ke trace request API yang mengirim event.
"""
import json
import logging

import pika
from opentelemetry import trace
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind

from app.infrastructure.metrics import EVENTS_PUBLISHED

EXCHANGE = "orders"
QUEUE = "notifications"
RETRY_QUEUE = "notifications.retry"
DEAD_LETTER_QUEUE = "notifications.dlq"
POINTS_QUEUE = "points"
POINTS_DEAD_LETTER_QUEUE = "points.dlq"

logger = logging.getLogger("app.events")
tracer = trace.get_tracer("app.events")


def connect(url: str) -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(url))


def declare_topology(channel) -> None:
    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(DEAD_LETTER_QUEUE, durable=True)
    channel.queue_declare(QUEUE, durable=True, arguments={
        "x-dead-letter-exchange": "", "x-dead-letter-routing-key": DEAD_LETTER_QUEUE})
    channel.queue_bind(QUEUE, EXCHANGE, routing_key="order.*")
    channel.queue_declare(RETRY_QUEUE, durable=True, arguments={
        "x-dead-letter-exchange": "", "x-dead-letter-routing-key": QUEUE})
    channel.queue_declare(POINTS_DEAD_LETTER_QUEUE, durable=True)
    channel.queue_declare(POINTS_QUEUE, durable=True, arguments={
        "x-dead-letter-exchange": "", "x-dead-letter-routing-key": POINTS_DEAD_LETTER_QUEUE})
    channel.queue_bind(POINTS_QUEUE, EXCHANGE, routing_key="order.paid")


class RabbitMQPublisher:
    """Satu koneksi per publish supaya sederhana. Di traffic tinggi, koneksi sebaiknya dipakai ulang."""

    def __init__(self, url: str):
        self.url = url

    def publish(self, event: dict) -> None:
        fields = {"event_type": event["type"], "event_id": event["event_id"]}
        with tracer.start_as_current_span(f"publish {event['type']}", kind=SpanKind.PRODUCER):
            try:
                with connect(self.url) as connection:
                    channel = connection.channel()
                    channel.confirm_delivery()              # tunggu RabbitMQ konfirmasi pesan diterima
                    declare_topology(channel)
                    channel.basic_publish(EXCHANGE, event["type"], json.dumps(event), message_properties(event))
                EVENTS_PUBLISHED.labels(event["type"], "ok").inc()
                logger.info("event dikirim", extra=fields)
            except pika.exceptions.AMQPError:
                # order sudah ter-commit, jadi request tidak digagalkan. Event-nya hilang dan tercatat di log.
                EVENTS_PUBLISHED.labels(event["type"], "failed").inc()
                logger.exception("gagal publish event", extra={**fields, "error_type": "dependency"})


def message_properties(event: dict) -> pika.BasicProperties:
    headers = {}
    inject(headers)                                         # tulis traceparent dari span yang sedang aktif
    return pika.BasicProperties(
        content_type="application/json", message_id=event["event_id"], headers=headers,
        delivery_mode=pika.DeliveryMode.Persistent)
