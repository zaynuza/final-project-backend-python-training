"""Fake adapter untuk unit test use case. Bentuknya sama dengan port, isinya cuma dict."""
import threading

from app.application.auth_service import CurrentUser
from app.domain.order import Order, OrderStatus
from app.domain.product import Product
from app.domain.user import ROLE_SCOPES, User
from app.domain.voucher import Voucher


def actor(email: str = "budi@mail.com", customer_type: str = "vip", role: str = "customer") -> CurrentUser:
    """User yang sedang login, untuk memanggil use case langsung di unit test."""
    return CurrentUser(email, role, customer_type, frozenset(ROLE_SCOPES[role]))


ADMIN = actor("admin@toko.com", "regular", "admin")


class FakeProductRepository:
    def __init__(self, products: list[Product] = ()):
        self.rows: dict[int, Product] = {}
        for product in products:
            self.add(product)

    def add(self, product: Product) -> Product:
        product.id = len(self.rows) + 1
        self.rows[product.id] = product
        return product

    def get(self, product_id: int) -> Product | None:
        return self.rows.get(product_id)

    get_for_update = get                       # fake tidak punya transaksi bersamaan, jadi tidak perlu kunci

    def list(self) -> list[Product]:
        return list(self.rows.values())

    def save(self, product: Product) -> None:
        self.rows[product.id] = product


class FakeOrderRepository:
    def __init__(self):
        self.rows: dict[int, Order] = {}

    def add(self, order: Order) -> Order:
        order.id = len(self.rows) + 1
        self.rows[order.id] = order
        return order

    def get(self, order_id: int) -> Order | None:
        return self.rows.get(order_id)

    get_for_update = get

    def list_for_customer(self, customer: str, limit: int, after: int | None = None) -> list[Order]:
        orders = sorted((o for o in self.rows.values() if o.customer == customer and (after is None or o.id < after)),
                        key=lambda o: o.id, reverse=True)
        return orders[:limit]

    def sales_summary(self) -> dict:
        orders = list(self.rows.values())
        paid = [o for o in orders if o.status == OrderStatus.PAID]
        return {"total_orders": len(orders), "paid_orders": len(paid),
                "cancelled_orders": sum(o.status == OrderStatus.CANCELLED for o in orders),
                "revenue": sum(o.total.amount for o in paid)}

    def save(self, order: Order) -> None:
        self.rows[order.id] = order


class FakeVoucherRepository:
    def __init__(self, vouchers: list[Voucher] = ()):
        self.rows: dict[str, Voucher] = {}
        for voucher in vouchers:
            self.add(voucher)

    def add(self, voucher: Voucher) -> Voucher:
        self.rows[voucher.code] = voucher
        return voucher

    def get(self, code: str) -> Voucher | None:
        return self.rows.get(code)

    get_for_update = get

    def save(self, voucher: Voucher) -> None:
        self.rows[voucher.code] = voucher


class FakeUserRepository:
    def __init__(self):
        self.rows: dict[str, User] = {}

    def add(self, user: User) -> User:
        user.id = len(self.rows) + 1
        self.rows[user.email] = user
        return user

    def get_by_email(self, email: str) -> User | None:
        return self.rows.get(email)


class FakeUnitOfWork:
    def __init__(self, products: list[Product] = (), vouchers: list[Voucher] = ()):
        self.products = FakeProductRepository(products)
        self.vouchers = FakeVoucherRepository(vouchers)
        self.orders = FakeOrderRepository()
        self.users = FakeUserRepository()
        self.committed = False

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, *exc) -> None:
        pass

    def commit(self) -> None:
        self.committed = True


class FakeEventPublisher:
    def __init__(self):
        self.published: list[dict] = []

    def publish(self, event: dict) -> None:
        self.published.append(event)


class FakeNotifier:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, message: str) -> None:
        self.sent.append((to, message))


class FakeNotificationLog:
    def __init__(self):
        self.keys: set[str] = set()

    def already_sent(self, key: str) -> bool:
        return key in self.keys

    def mark_sent(self, key: str) -> None:
        self.keys.add(key)


class FakeCache:
    def __init__(self):
        self.rows: dict = {}
        self.locks: set[str] = set()
        self._guard = threading.Lock()

    def get(self, key: str):
        return self.rows.get(key)

    def set(self, key: str, value) -> None:
        self.rows[key] = value

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.rows.pop(key, None)

    def acquire_lock(self, key: str, ttl: int = 5) -> bool:
        with self._guard:                         # hanya satu thread yang berhasil, seperti SET NX di Redis
            if key in self.locks:
                return False
            self.locks.add(key)
            return True

    def release_lock(self, key: str) -> None:
        self.locks.discard(key)
