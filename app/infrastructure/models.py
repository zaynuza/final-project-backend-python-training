"""Infrastructure: ORM model (bentuk tabel). Tidak berisi business logic.

Index dibuat sesuai query yang sering dipakai:
- orders (customer, id)   : riwayat order customer, urut dari yang terbaru
- order_lines (order_id)  : ambil item sebuah order. PostgreSQL tidak membuat index foreign key otomatis
"""
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class ProductRecord(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int]
    stock: Mapped[int]


class OrderRecord(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_customer_id", "customer", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer: Mapped[str] = mapped_column(String(100))
    customer_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    discount: Mapped[int]
    voucher_code: Mapped[str | None] = mapped_column(String(30))
    lines: Mapped[list["OrderLineRecord"]] = relationship(cascade="all, delete-orphan")


class OrderLineRecord(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product: Mapped[str] = mapped_column(String(100))
    price: Mapped[int]
    qty: Mapped[int]


class VoucherRecord(Base):
    """Voucher belanja. Kuota dikurangi dalam transaksi yang sama dengan stok dan order."""
    __tablename__ = "vouchers"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)    # primary key = unique + ber-index
    amount: Mapped[int]
    quota: Mapped[int]


class UserRecord(Base):
    """User yang bisa login. Password hanya disimpan sebagai hash Argon2."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    customer_type: Mapped[str] = mapped_column(String(20))


class CustomerPointsRecord(Base):
    """Saldo poin loyalty per customer."""
    __tablename__ = "customer_points"

    customer: Mapped[str] = mapped_column(String(100), primary_key=True)
    points: Mapped[int]


class PointEventRecord(Base):
    """Event yang poinnya sudah ditambahkan. event_id primary key, jadi satu event hanya tercatat sekali."""
    __tablename__ = "point_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer: Mapped[str] = mapped_column(String(100))
    points: Mapped[int]


class SentNotificationRecord(Base):
    """Notifikasi yang sudah terkirim. key = event_id, unique karena primary key."""
    __tablename__ = "sent_notifications"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(server_default=func.now())
