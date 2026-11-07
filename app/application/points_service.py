"""Application: use case poin loyalty dari event order.

Setiap order yang dibayar (order.paid) memberi 1 poin per Rp10.000 dari total order.
Dipanggil oleh consumer RabbitMQ, tidak tahu apa-apa soal RabbitMQ.
Idempotent: PointsLedger mencatat event_id dalam transaksi yang sama dengan penambahan poin,
jadi event yang datang dua kali tidak menambah poin dua kali.
"""
from app.application.auth_service import CurrentUser
from app.application.errors import AccessDenied, InvalidEvent
from app.application.events import ORDER_PAID
from app.application.ports import PointsLedger

POINT_VALUE = 10_000                  # 1 poin per Rp10.000


class PointsService:
    def __init__(self, ledger: PointsLedger):
        self.ledger = ledger

    def handle(self, event: dict) -> str:
        try:
            event_id, event_type = event["event_id"], event["type"]
            customer, total = event["customer"], int(event["total"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidEvent(f"event tidak valid: {exc}") from exc

        if event_type != ORDER_PAID:
            return "ignored"
        points = total // POINT_VALUE
        if not self.ledger.add(event_id, customer, points):
            return "skipped"
        return "added"

    def balance(self, customer: str, actor: CurrentUser | None = None) -> int:
        if actor is not None and customer != actor.email and not actor.can("orders:all"):
            raise AccessDenied("Hanya bisa melihat saldo poin milik sendiri")
        return self.ledger.balance(customer)
