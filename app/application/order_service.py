"""Application: use case order.

Setiap use case berjalan dalam satu Unit of Work (satu transaksi):
- place_order  : kurangi stok semua item + pakai kuota voucher + simpan order
- cancel_order : kembalikan stok semua item + kembalikan kuota voucher + ubah status
- list_orders  : riwayat order customer per halaman (keyset pagination)
Kalau satu langkah gagal, semua langkah dibatalkan (rollback).

Dua request bersamaan: baris yang akan diubah dikunci dulu (SELECT ... FOR UPDATE), jadi request kedua menunggu
request pertama selesai lalu membaca nilai yang sudah terbaru. Tanpa itu, kuota voucher 1 bisa terpakai dua kali
dan stok bisa terhitung lebih banyak dari yang sebenarnya.
Urutan kunci SELALU sama (order -> produk urut id -> voucher), supaya dua transaksi tidak saling menunggu (deadlock).
Setelah commit, use case mengumumkan event (order.placed, order.paid, order.cancelled).
Event tidak dikirim kalau transaksinya gagal, jadi tidak ada notifikasi untuk order yang batal tersimpan.

Hak akses: setiap use case menerima actor (user yang sedang login).
- Order baru selalu atas nama actor, dengan customer_type dari data user, bukan dari body request
- Order milik customer lain dianggap tidak ada (404), kecuali actor punya scope orders:all
"""
from app.application.auth_service import CurrentUser
from app.application.errors import AccessDenied, OrderNotFound, ProductNotFound, VoucherNotFound
from app.application.events import ORDER_CANCELLED, ORDER_PAID, ORDER_PLACED, order_event
from app.application.ports import EventPublisher, UnitOfWork
from app.domain.discount_policy import DiscountPolicy
from app.domain.order import Order
from app.domain.product import Product
from app.domain.voucher import Voucher


class OrderService:
    def __init__(self, uow: UnitOfWork, events: EventPublisher):
        self.uow = uow
        self.events = events
        self.discount_policy = DiscountPolicy()

    def place_order(self, actor: CurrentUser, items: list[dict], voucher_code: str | None = None) -> Order:
        with self.uow:
            products = self._lock_products([item["product_id"] for item in items])
            order = Order(actor.email, actor.customer_type)
            for item in items:
                product = products[item["product_id"]]
                product.reserve(item["qty"])
                order.add_item(product.id, product.name, product.price, item["qty"])
                self.uow.products.save(product)
            order.apply_discount(self.discount_policy.discount_for(order))
            if voucher_code:
                voucher = self._get_voucher(voucher_code)
                voucher.redeem()
                order.apply_voucher(voucher.code, voucher.amount)
                self.uow.vouchers.save(voucher)
            self.uow.orders.add(order)
            self.uow.commit()

        self.events.publish(order_event(ORDER_PLACED, order))
        return order

    def pay_order(self, order_id: int, actor: CurrentUser) -> Order:
        with self.uow:
            order = self._get_order(order_id, actor, lock=True)      # bayar dan batal tidak boleh jalan bersamaan
            order.pay()
            self.uow.orders.save(order)
            self.uow.commit()

        self.events.publish(order_event(ORDER_PAID, order))
        return order

    def cancel_order(self, order_id: int, actor: CurrentUser) -> Order:
        with self.uow:
            order = self._get_order(order_id, actor, lock=True)
            order.cancel()
            products = self._lock_products([line.product_id for line in order.lines])
            for line in order.lines:
                product = products[line.product_id]
                product.release(line.qty)
                self.uow.products.save(product)
            if order.voucher_code:
                voucher = self._get_voucher(order.voucher_code)
                voucher.restore()
                self.uow.vouchers.save(voucher)
            self.uow.orders.save(order)
            self.uow.commit()

        self.events.publish(order_event(ORDER_CANCELLED, order))
        return order

    def list_orders(self, actor: CurrentUser, customer: str | None = None, limit: int = 20,
                    after: int | None = None) -> list[Order]:
        customer = customer or actor.email
        if customer != actor.email and not actor.can("orders:all"):
            raise AccessDenied("Hanya bisa melihat riwayat order sendiri")
        with self.uow:
            return self.uow.orders.list_for_customer(customer, limit, after)

    def get_order(self, order_id: int, actor: CurrentUser) -> Order:
        with self.uow:
            return self._get_order(order_id, actor)

    def _get_order(self, order_id: int, actor: CurrentUser, lock: bool = False) -> Order:
        order = self.uow.orders.get_for_update(order_id) if lock else self.uow.orders.get(order_id)
        # order milik orang lain = 404, bukan 403, supaya keberadaan order tidak bocor
        if order is None or (order.customer != actor.email and not actor.can("orders:all")):
            raise OrderNotFound(f"Order #{order_id} tidak ditemukan")
        return order

    def _lock_products(self, product_ids: list[int]) -> dict[int, Product]:
        """Kunci semua produk yang akan diubah, urut id. Urutan yang sama di semua use case mencegah deadlock."""
        products = {}
        for product_id in sorted(set(product_ids)):
            product = self.uow.products.get_for_update(product_id)
            if product is None:
                raise ProductNotFound(f"Product #{product_id} tidak ditemukan")
            products[product_id] = product
        return products

    def _get_voucher(self, code: str) -> Voucher:
        voucher = self.uow.vouchers.get_for_update(code)            # voucher selalu diubah setelah dibaca
        if voucher is None:
            raise VoucherNotFound(f"Voucher {code} tidak ditemukan")
        return voucher
