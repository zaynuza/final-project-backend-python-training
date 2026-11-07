"""Infrastructure: adapter untuk port Notifier + factory-nya.

Adapter di sini benar-benar mengirim (simulasi). Yang memanggilnya adalah consumer RabbitMQ,
bukan request API. fail_rate dipakai untuk mensimulasikan server email yang sedang gangguan.
"""
import random

from app.application.ports import Notifier


class NotificationServiceDown(Exception):
    """Server email/SMS sedang gangguan. Sifatnya sementara, jadi aman untuk di-retry."""


class EmailNotifier:
    def __init__(self, fail_rate: float = 0.0):
        self.fail_rate = fail_rate

    def send(self, to: str, message: str) -> None:
        if random.random() < self.fail_rate:
            raise NotificationServiceDown("Server email timeout")
        print(f"[EMAIL] ke {to}: {message}")


class SmsNotifier:
    def __init__(self, fail_rate: float = 0.0):
        self.fail_rate = fail_rate

    def send(self, to: str, message: str) -> None:
        if random.random() < self.fail_rate:
            raise NotificationServiceDown("Gateway SMS timeout")
        print(f"[SMS] ke {to}: {message}")


NOTIFIERS = {"email": EmailNotifier, "sms": SmsNotifier}


def create_notifier(channel: str, fail_rate: float = 0.0) -> Notifier:
    if channel not in NOTIFIERS:
        raise ValueError(f"Channel tidak dikenal: {channel}")
    return NOTIFIERS[channel](fail_rate)
