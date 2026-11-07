"""Domain: value object Money. Dikenali dari nilainya, immutable, tidak mungkin negatif."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: int

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Money tidak boleh negatif")

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.amount - other.amount)

    def times(self, qty: int) -> "Money":
        return Money(self.amount * qty)

    def percent(self, value: int) -> "Money":
        return Money(self.amount * value // 100)
