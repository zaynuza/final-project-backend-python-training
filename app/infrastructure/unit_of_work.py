"""Infrastructure: Unit of Work berbasis SQLAlchemy Session.

Satu `with uow:` = satu session = satu transaksi.
Semua repository di dalamnya memakai session yang sama.

Setelah commit berhasil, cache produk yang berubah dihapus (invalidation).
Dihapus SETELAH commit, supaya tidak ada request lain yang mengisi cache dengan data yang belum tersimpan.
Cache produk terlaris ikut dihapus setiap ada status order yang berubah (misalnya order dibayar).
"""
from sqlalchemy.orm import sessionmaker

from app.application.cache_keys import BEST_SELLERS_KEY, PRODUCT_LIST_KEY, product_key
from app.application.ports import Cache
from app.infrastructure.repositories import (
    SqlAlchemyOrderRepository,
    SqlAlchemyProductRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyVoucherRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker, cache: Cache | None = None):
        self.session_factory = session_factory
        self.cache = cache

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self.session_factory()
        self.orders = SqlAlchemyOrderRepository(self.session)
        self.products = SqlAlchemyProductRepository(self.session)
        self.vouchers = SqlAlchemyVoucherRepository(self.session)
        self.users = SqlAlchemyUserRepository(self.session)
        return self

    def __exit__(self, *exc) -> None:
        self.session.rollback()      # sudah commit = tidak berefek, belum commit / error = dibatalkan
        self.session.close()

    def commit(self) -> None:
        self.session.commit()
        if self.cache and self.products.changed_ids:
            self.cache.delete(PRODUCT_LIST_KEY, *(product_key(i) for i in self.products.changed_ids))
            self.products.changed_ids.clear()
        if self.cache and self.orders.status_changed:
            self.cache.delete(BEST_SELLERS_KEY)               # angka terjual berubah, hitung ulang
            self.orders.status_changed = False
