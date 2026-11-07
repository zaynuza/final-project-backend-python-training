"""API: endpoint voucher. Membuat dan melihat voucher khusus admin (scope products:write).

Memakai voucher dilakukan lewat POST /orders (field voucher_code), bukan di sini.
"""
from fastapi import APIRouter, Depends, Security

from app.api.dependencies import get_voucher_service
from app.api.schemas import ErrorOut, VoucherIn, VoucherOut
from app.api.security import get_current_user
from app.application.voucher_service import VoucherService

router = APIRouter(prefix="/vouchers", tags=["vouchers"],
                   dependencies=[Security(get_current_user, scopes=["products:write"])],
                   responses={401: {"model": ErrorOut, "description": "Belum login"},
                              403: {"model": ErrorOut, "description": "Butuh scope products:write"}})


@router.post("", status_code=201, response_model=VoucherOut, summary="Buat voucher (admin)",
             responses={409: {"model": ErrorOut, "description": "Kode voucher sudah dipakai"}})
def create_voucher(payload: VoucherIn, service: VoucherService = Depends(get_voucher_service)):
    return VoucherOut.from_domain(service.create_voucher(payload.code, payload.amount, payload.quota))


@router.get("/{code}", response_model=VoucherOut, summary="Detail voucher dan sisa kuota (admin)",
            responses={404: {"model": ErrorOut, "description": "Voucher tidak ditemukan"}})
def get_voucher(code: str, service: VoucherService = Depends(get_voucher_service)):
    return VoucherOut.from_domain(service.get_voucher(code))
