"""Domain: domain service DiscountPolicy.

Besar diskon bergantung pada tipe customer dan subtotal order,
jadi aturannya ditaruh di service sendiri, bukan di dalam Order.
Strategy dari Sesi 1 tetap dipakai di sini, sekarang dalam bentuk Money.
"""
from typing import Protocol

from app.domain.errors import UnknownCustomerType
from app.domain.money import Money
from app.domain.order import Order


class DiscountStrategy(Protocol):
    def discount(self, subtotal: Money) -> Money: ...


class NoDiscount:
    def discount(self, subtotal: Money) -> Money:
        return Money(0)


class PercentDiscount:
    def __init__(self, percent: int):
        self.percent = percent

    def discount(self, subtotal: Money) -> Money:
        return subtotal.percent(self.percent)


DISCOUNTS: dict[str, DiscountStrategy] = {
    "regular": NoDiscount(),
    "member": PercentDiscount(5),
    "vip": PercentDiscount(10),
}


class DiscountPolicy:
    def discount_for(self, order: Order) -> Money:
        if order.customer_type not in DISCOUNTS:
            raise UnknownCustomerType("Tipe customer tidak dikenal")
        return DISCOUNTS[order.customer_type].discount(order.subtotal)
