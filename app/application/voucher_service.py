"""Application: use case voucher."""
from app.application.errors import VoucherNotFound
from app.application.ports import UnitOfWork
from app.domain.errors import VoucherAlreadyExists
from app.domain.money import Money
from app.domain.voucher import Voucher


class VoucherService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def create_voucher(self, code: str, amount: int, quota: int) -> Voucher:
        with self.uow:
            if self.uow.vouchers.get(code) is not None:
                raise VoucherAlreadyExists(f"Voucher {code} sudah ada")
            voucher = self.uow.vouchers.add(Voucher(code, Money(amount), quota))
            self.uow.commit()
        return voucher

    def get_voucher(self, code: str) -> Voucher:
        with self.uow:
            voucher = self.uow.vouchers.get(code)
        if voucher is None:
            raise VoucherNotFound(f"Voucher {code} tidak ditemukan")
        return voucher
