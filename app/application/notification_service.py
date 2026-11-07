"""Application: use case kirim notifikasi dari event order.

Dipanggil oleh consumer RabbitMQ, tidak tahu apa-apa soal RabbitMQ.
Idempotent: event_id yang sudah tercatat di NotificationLog tidak dikirim lagi,
jadi event yang datang dua kali (redelivery) tidak membuat email dobel.
"""
from app.application.errors import InvalidEvent
from app.application.events import ORDER_CANCELLED, ORDER_PAID, ORDER_PLACED
from app.application.ports import NotificationLog, Notifier

MESSAGES = {
    ORDER_PLACED: "Order #{order_id} total Rp{total:,}",
    ORDER_PAID: "Order #{order_id} sudah dibayar",
    ORDER_CANCELLED: "Order #{order_id} dibatalkan",
}


class NotificationService:
    def __init__(self, notifier: Notifier, log: NotificationLog):
        self.notifier = notifier
        self.log = log

    def handle(self, event: dict) -> str:
        try:
            key, to, template = event["event_id"], event["customer"], MESSAGES[event["type"]]
            message = template.format(**event)
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidEvent(f"event tidak valid: {exc}") from exc

        if self.log.already_sent(key):
            return "skipped"
        self.notifier.send(to, message)
        self.log.mark_sent(key)
        return "sent"
