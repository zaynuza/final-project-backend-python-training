"""Application: event order.

Event = fakta yang sudah terjadi (order.placed, order.paid, order.cancelled), bukan perintah.
OrderService cukup mengumumkan event, tidak perlu tahu siapa yang mendengar.
event_id dibuat unik di sini, dipakai consumer untuk idempotency.
"""
import uuid
from datetime import datetime, timezone

from app.domain.order import Order

ORDER_PLACED = "order.placed"
ORDER_PAID = "order.paid"
ORDER_CANCELLED = "order.cancelled"


def order_event(event_type: str, order: Order) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "order_id": order.id,
        "customer": order.customer,
        "total": order.total.amount,
    }
