"""API: schema request & response (Pydantic). Ini juga yang tampil di /docs."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.order import Order
from app.domain.product import Product
from app.domain.voucher import Voucher


# ---------- product ----------
class ProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")              # field di luar schema = 422

    name: str = Field(min_length=1, max_length=100, examples=["Keyboard"])
    price: int = Field(gt=0, le=1_000_000_000, examples=[500_000])
    stock: int = Field(ge=0, le=1_000_000, examples=[10])


class ProductOut(BaseModel):
    id: int
    name: str
    price: int
    stock: int

    @classmethod
    def from_domain(cls, product: Product) -> "ProductOut":
        return cls(id=product.id, name=product.name, price=product.price.amount, stock=product.stock)


class BestSellerOut(BaseModel):
    product_id: int
    name: str
    sold: int = Field(description="Jumlah terjual dari order yang sudah dibayar")


# ---------- order ----------
class OrderItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0, examples=[1])
    qty: int = Field(gt=0, le=100, examples=[2])


class OrderIn(BaseModel):
    """customer dan customer_type tidak ada di sini: diambil dari token user yang login."""
    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    voucher_code: str | None = Field(None, min_length=3, max_length=30, examples=["HEMAT50"])


class OrderLineOut(BaseModel):
    product_id: int
    name: str
    price: int
    qty: int


class OrderOut(BaseModel):
    id: int
    customer: str
    customer_type: str
    status: str
    items: list[OrderLineOut]
    subtotal: int
    discount: int
    total: int
    voucher_code: str | None = None

    @classmethod
    def from_domain(cls, order: Order) -> "OrderOut":
        return cls(
            id=order.id, customer=order.customer, customer_type=order.customer_type,
            status=order.status.value,
            items=[OrderLineOut(product_id=line.product_id, name=line.product,
                                price=line.price.amount, qty=line.qty) for line in order.lines],
            subtotal=order.subtotal.amount, discount=order.discount.amount, total=order.total.amount,
            voucher_code=order.voucher_code,
        )


class OrderPageOut(BaseModel):
    items: list[OrderOut]
    next_after: int | None = Field(
        description="Kirim sebagai ?after= untuk halaman berikutnya. null = halaman terakhir")


# ---------- voucher ----------
class VoucherIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=3, max_length=30, pattern=r"^[A-Z0-9_-]+$", examples=["HEMAT50"])
    amount: int = Field(gt=0, le=100_000_000, examples=[50_000])
    quota: int = Field(ge=0, le=1_000_000, examples=[2])


class VoucherOut(BaseModel):
    code: str
    amount: int
    quota: int

    @classmethod
    def from_domain(cls, voucher: Voucher) -> "VoucherOut":
        return cls(code=voucher.code, amount=voucher.amount.amount, quota=voucher.quota)


# ---------- report ----------
class SalesReportOut(BaseModel):
    total_orders: int
    paid_orders: int
    cancelled_orders: int
    revenue: int


class JobOut(BaseModel):
    task_id: str
    status: str = Field(examples=["pending"])
    status_url: str


class ReportStatusOut(BaseModel):
    task_id: str
    status: str = Field(description="pending, running, retrying, done, atau failed", examples=["done"])
    result: SalesReportOut | None = None
    error: str | None = None


# ---------- customer ----------
class PointsOut(BaseModel):
    customer: str
    points: int = Field(description="Saldo poin loyalty, 1 poin per Rp10.000 dari order yang dibayar")


# ---------- auth ----------
class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int                        # detik


class MeOut(BaseModel):
    email: str
    role: str
    customer_type: str
    scopes: list[str]


# ---------- ops ----------
class ReadinessOut(BaseModel):
    status: str                            # ready / not_ready
    checks: dict[str, str]                 # nama dependency -> "ok" atau "down: <error>"


# ---------- error ----------
class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None
    request_id: str | None = None          # sama dengan header X-Request-ID, untuk dicari di log


class ErrorOut(BaseModel):
    error: ErrorBody
