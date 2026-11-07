"""Application: use case product.

Baca produk memakai cache-aside: cek cache dulu, kalau tidak ada baru ke database lalu simpan ke cache.
Cache dihapus (invalidation) oleh Unit of Work setiap ada produk yang berubah, setelah commit.
Produk terlaris di-cache sebagai top 10, lalu dipotong sesuai limit, jadi cukup satu cache key.

Cache stampede: saat cache kosong, hanya SATU request yang mengambil lock lalu query database dan mengisi cache.
Request lain menunggu sebentar lalu membaca hasilnya dari cache, jadi database tidak diserbu banyak query kembar.
"""
import time

from app.application.cache_keys import BEST_SELLERS_KEY, PRODUCT_LIST_KEY, product_key
from app.application.errors import ProductNotFound
from app.application.ports import Cache, UnitOfWork
from app.domain.money import Money
from app.domain.product import Product

MAX_BEST_SELLERS = 10
LOCK_WAIT = 0.05            # detik jeda antar percobaan saat request lain sedang mengisi cache
LOCK_ATTEMPTS = 20          # menunggu maksimal ~1 detik, lock sendiri kedaluwarsa dalam 5 detik


class ProductService:
    def __init__(self, uow: UnitOfWork, cache: Cache):
        self.uow = uow
        self.cache = cache

    def create_product(self, name: str, price: int, stock: int) -> Product:
        with self.uow:
            product = self.uow.products.add(Product(name, Money(price), stock))
            self.uow.commit()
        return product

    def list_products(self) -> list[Product]:
        def query() -> list[dict]:
            with self.uow:
                return [_to_dict(p) for p in self.uow.products.list()]

        rows, _ = self._cache_aside(PRODUCT_LIST_KEY, query)
        return [_from_dict(row) for row in rows]

    def get_product(self, product_id: int) -> Product:
        def query() -> dict:
            with self.uow:
                product = self.uow.products.get(product_id)
            if product is None:
                raise ProductNotFound(f"Product #{product_id} tidak ditemukan")
            return _to_dict(product)

        row, _ = self._cache_aside(product_key(product_id), query)
        return _from_dict(row)

    def best_sellers(self, limit: int) -> tuple[list[dict], bool]:
        """Produk terlaris dari order yang sudah dibayar. Kembalikan (data, cache_hit)."""
        def query() -> list[dict]:
            with self.uow:
                return self.uow.orders.best_sellers(MAX_BEST_SELLERS)

        rows, cache_hit = self._cache_aside(BEST_SELLERS_KEY, query)
        return rows[:limit], cache_hit

    def _cache_aside(self, key: str, query):
        """Cache-aside dengan lock anti-stampede. Kembalikan (nilai, cache_hit)."""
        for _ in range(LOCK_ATTEMPTS):
            cached = self.cache.get(key)
            if cached is not None:
                return cached, True
            if self.cache.acquire_lock(key):                  # hanya satu request yang lolos ke sini
                try:
                    cached = self.cache.get(key)              # cek lagi: mungkin baru diisi pemegang lock sebelumnya
                    if cached is not None:
                        return cached, True
                    value = query()
                    self.cache.set(key, value)
                    return value, False
                finally:
                    self.cache.release_lock(key)              # selalu dilepas, juga saat query error
            time.sleep(LOCK_WAIT)                             # yang lain menunggu, lalu cek cache lagi
        return query(), False                                 # lock macet terlalu lama: jangan gagalkan request


def _to_dict(product: Product) -> dict:
    return {"id": product.id, "name": product.name, "price": product.price.amount, "stock": product.stock}


def _from_dict(row: dict) -> Product:
    return Product(row["name"], Money(row["price"]), row["stock"], id=row["id"])
