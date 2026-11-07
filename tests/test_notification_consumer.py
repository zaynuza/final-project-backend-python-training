"""Test consumer notifikasi tanpa RabbitMQ.

FakeChannel mencatat ack, nack, dan publish ke retry queue, jadi keputusan consumer bisa dicek langsung:
berhasil -> ack, pesan dobel -> skip + ack, gangguan -> retry dengan jeda, rusak / lewat batas -> DLQ.
"""
import json
from types import SimpleNamespace

import pytest

from app.application.notification_service import NotificationService
from app.consumers.notification_consumer import process_message
from app.infrastructure.database import create_session_factory
from app.infrastructure.notification_log import SqlAlchemyNotificationLog
from app.infrastructure.notifiers import NotificationServiceDown
from app.infrastructure.rabbitmq import RETRY_QUEUE
from tests.fakes import FakeNotificationLog, FakeNotifier

EVENT = {"event_id": "evt-1", "type": "order.placed", "order_id": 1, "customer": "budi@mail.com", "total": 900_000}


class FakeChannel:
    def __init__(self):
        self.acked, self.nacked, self.published = [], [], []

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag, requeue=True):
        self.nacked.append((delivery_tag, requeue))

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append((routing_key, body, properties))


class DownNotifier:
    def send(self, to: str, message: str) -> None:
        raise NotificationServiceDown("Server email timeout")


def deliver(service, body, retries=0, tag=1):
    channel = FakeChannel()
    properties = SimpleNamespace(headers={"x-retries": retries} if retries else None, message_id="evt-1")
    result = process_message(channel, SimpleNamespace(delivery_tag=tag), properties, body, service,
                             max_retries=3, retry_delay_ms=1000)
    return result, channel


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def service(notifier):
    return NotificationService(notifier, FakeNotificationLog())


def test_event_berhasil_dikirim_lalu_ack(service, notifier):
    result, channel = deliver(service, json.dumps(EVENT))
    assert result == "sent"
    assert notifier.sent == [("budi@mail.com", "Order #1 total Rp900,000")]
    assert channel.acked == [1] and channel.nacked == []


def test_event_dobel_hanya_dikirim_sekali(service, notifier):
    deliver(service, json.dumps(EVENT))
    result, channel = deliver(service, json.dumps(EVENT), tag=2)      # redelivery, event_id sama
    assert result == "skipped"
    assert len(notifier.sent) == 1
    assert channel.acked == [2]                                       # tetap di-ack supaya tidak datang lagi


def test_idempotent_dengan_database_sungguhan(notifier):
    service = NotificationService(notifier, SqlAlchemyNotificationLog(create_session_factory("sqlite://")))
    assert [deliver(service, json.dumps(EVENT))[0] for _ in range(3)] == ["sent", "skipped", "skipped"]
    assert len(notifier.sent) == 1


@pytest.mark.parametrize("retries, delay", [(0, "1000"), (1, "2000"), (2, "4000")])
def test_gangguan_sementara_dikirim_ke_retry_queue_dengan_jeda(retries, delay):
    service = NotificationService(DownNotifier(), FakeNotificationLog())
    result, channel = deliver(service, json.dumps(EVENT), retries=retries)

    assert result == "retrying"
    (queue, body, properties), = channel.published
    assert queue == RETRY_QUEUE and json.loads(body) == EVENT
    assert properties.expiration == delay                             # jeda 2x lipat setiap retry
    assert properties.headers == {"x-retries": retries + 1}
    assert channel.acked == [1]                                       # pesan lama di-ack, salinannya menunggu


def test_lewat_batas_retry_masuk_dlq():
    service = NotificationService(DownNotifier(), FakeNotificationLog())
    result, channel = deliver(service, json.dumps(EVENT), retries=3)
    assert result == "dead_lettered"
    assert channel.nacked == [(1, False)] and channel.published == []


@pytest.mark.parametrize("body", [b"bukan json", json.dumps({"type": "order.placed"}),
                                  json.dumps({**EVENT, "type": "order.unknown"})])
def test_pesan_rusak_langsung_dlq_tanpa_retry(service, notifier, body):
    result, channel = deliver(service, body)
    assert result == "dead_lettered"
    assert channel.nacked == [(1, False)] and channel.published == []
    assert notifier.sent == []
