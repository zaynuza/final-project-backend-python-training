"""Domain: entity Voucher. Kuota hanya berubah lewat redeem() dan restore()."""
from app.domain.errors import VoucherExhausted
from app.domain.money import Money


class Voucher:
    def __init__(self, code: str, amount: Money, quota: int):
        if quota < 0:
            raise ValueError("Kuota tidak boleh negatif")
        self.code = code
        self.amount = amount
        self.quota = quota

    def redeem(self) -> None:
        if self.quota == 0:
            raise VoucherExhausted(f"Kuota voucher {self.code} sudah habis")
        self.quota -= 1

    def restore(self) -> None:
        self.quota += 1
