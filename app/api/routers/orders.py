"""API: endpoint order.

Tidak ada try/except di sini. Error dari service naik ke exception handler global (api/errors.py).
Semua endpoint order dibatasi rate limit per client (api/rate_limit.py) dan butuh login dengan scope
orders:write. Hak akses per order (milik sendiri atau admin) dicek di OrderService.
"""
from fastapi import APIRouter, Depends, Query, Security

from app.api.dependencies import get_order_service
from app.api.rate_limit import rate_limit
from app.api.schemas import ErrorOut, OrderIn, OrderOut, OrderPageOut
from app.api.security import get_current_user
from app.application.auth_service import CurrentUser
from app.application.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(rate_limit)],
                   responses={401: {"model": ErrorOut, "description": "Belum login atau token tidak valid"},
                              403: {"model": ErrorOut, "description": "Tidak punya scope yang dibutuhkan"},
                              429: {"model": ErrorOut, "description": "Terlalu banyak request (rate limit)"}})

NOT_FOUND = {404: {"model": ErrorOut, "description": "Order, produk, atau voucher tidak ditemukan"}}
CONFLICT = {409: {"model": ErrorOut, "description": "Stok kurang, kuota voucher habis, atau status order tidak sesuai"}}
Customer = Security(get_current_user, scopes=["orders:write"])


@router.post("", status_code=201, response_model=OrderOut, summary="Buat order atas nama user yang login",
             responses={**NOT_FOUND, **CONFLICT})
def create_order(payload: OrderIn, user: CurrentUser = Customer,
                 service: OrderService = Depends(get_order_service)):
    items = [i.model_dump() for i in payload.items]
    return OrderOut.from_domain(service.place_order(user, items, payload.voucher_code))


@router.get("", response_model=OrderPageOut, summary="Riwayat order (keyset pagination)")
def list_orders(customer: str | None = Query(None, description="Khusus admin, default: user yang login"),
                limit: int = Query(20, ge=1, le=100),
                after: int | None = Query(None, description="id order terakhir dari halaman sebelumnya"),
                user: CurrentUser = Customer, service: OrderService = Depends(get_order_service)):
    orders = service.list_orders(user, customer, limit, after)
    next_after = orders[-1].id if len(orders) == limit else None
    return OrderPageOut(items=[OrderOut.from_domain(o) for o in orders], next_after=next_after)


@router.get("/{order_id}", response_model=OrderOut, summary="Detail order", responses=NOT_FOUND)
def get_order(order_id: int, user: CurrentUser = Customer, service: OrderService = Depends(get_order_service)):
    return OrderOut.from_domain(service.get_order(order_id, user))


@router.post("/{order_id}/pay", response_model=OrderOut, summary="Bayar order",
             responses={**NOT_FOUND, **CONFLICT})
def pay_order(order_id: int, user: CurrentUser = Customer, service: OrderService = Depends(get_order_service)):
    return OrderOut.from_domain(service.pay_order(order_id, user))


@router.post("/{order_id}/cancel", response_model=OrderOut,
             summary="Batalkan order (stok dan kuota voucher dikembalikan)",
             responses={**NOT_FOUND, **CONFLICT})
def cancel_order(order_id: int, user: CurrentUser = Customer,
                 service: OrderService = Depends(get_order_service)):
    return OrderOut.from_domain(service.cancel_order(order_id, user))
