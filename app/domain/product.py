"""Domain: entity Product. Stok hanya berubah lewat reserve() dan release()."""
from app.domain.errors import OutOfStock
from app.domain.money import Money


class Product:
    def __init__(self, name: str, price: Money, stock: int, *, id: int | None = None):
        if stock < 0:
            raise ValueError("Stok tidak boleh negatif")
        self.id = id
        self.name = name
        self.price = price
        self.stock = stock

    def reserve(self, qty: int) -> None:
        if qty > self.stock:
            raise OutOfStock(f"Stok {self.name} tinggal {self.stock}")
        self.stock -= qty

    def release(self, qty: int) -> None:
        self.stock += qty

    def __eq__(self, other) -> bool:
        return isinstance(other, Product) and self.id is not None and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
