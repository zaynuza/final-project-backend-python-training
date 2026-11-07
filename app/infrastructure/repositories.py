"""Infrastructure: adapter SQLAlchemy untuk port repository.

Repository menerjemahkan domain model <-> ORM model, dan TIDAK pernah commit.
Commit adalah keputusan Unit of Work.
Product repository mencatat id produk yang berubah, supaya Unit of Work bisa menghapus cache-nya.

Order repository mencatat apakah ada status order yang berubah (untuk cache produk terlaris).

get_for_update: baca baris sambil menguncinya (SELECT ... FOR UPDATE) sampai transaksi selesai.
Dipakai oleh use case yang membaca lalu mengubah data (stok, kuota voucher, status order).
Tanpa kunci, dua request bersamaan sama-sama membaca nilai lama, lalu salah satu hasilnya tertimpa (lost update).
SQLite mengabaikan FOR UPDATE (database-nya sudah dikunci utuh saat menulis), PostgreSQL memakainya.

Optimasi query di order repository:
- list_for_customer : keyset pagination + selectinload (2 query, berapa pun jumlah order)
- sales_summary     : dihitung di database dengan satu query, bukan loop di Python
- best_sellers      : GROUP BY di database, hasilnya di-cache oleh ProductService
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.money import Money
from app.domain.order import Order, OrderLine, OrderStatus
from app.domain.product import Product
from app.domain.user import User
from app.domain.voucher import Voucher
from app.infrastructure.models import OrderLineRecord, OrderRecord, ProductRecord, UserRecord, VoucherRecord


class SqlAlchemyProductRepository:
    def __init__(self, session: Session):
        self.session = session
        self.changed_ids: set[int] = set()

    def add(self, product: Product) -> Product:
        record = ProductRecord(name=product.name, price=product.price.amount, stock=product.stock)
        self.session.add(record)
        self.session.flush()                  # minta id dari database, belum commit
        product.id = record.id
        self.changed_ids.add(product.id)
        return product

    def get(self, product_id: int) -> Product | None:
        record = self.session.get(ProductRecord, product_id)
        return self._to_domain(record) if record else None

    def get_for_update(self, product_id: int) -> Product | None:
        record = self.session.get(ProductRecord, product_id, with_for_update=True)   # kunci baris sampai commit
        return self._to_domain(record) if record else None

    def list(self) -> list[Product]:
        records = self.session.scalars(select(ProductRecord).order_by(ProductRecord.id))
        return [self._to_domain(r) for r in records]

    def save(self, product: Product) -> None:
        self.session.get(ProductRecord, product.id).stock = product.stock
        self.changed_ids.add(product.id)

    @staticmethod
    def _to_domain(record: ProductRecord) -> Product:
        return Product(record.name, Money(record.price), record.stock, id=record.id)


class SqlAlchemyOrderRepository:
    def __init__(self, session: Session):
        self.session = session
        self.status_changed = False

    def add(self, order: Order) -> Order:
        record = OrderRecord(
            customer=order.customer, customer_type=order.customer_type,
            status=order.status.value, discount=order.discount.amount, voucher_code=order.voucher_code,
            lines=[OrderLineRecord(product_id=line.product_id, product=line.product,
                                   price=line.price.amount, qty=line.qty) for line in order.lines],
        )
        self.session.add(record)
        self.session.flush()
        order.id = record.id
        return order

    def get(self, order_id: int) -> Order | None:
        record = self.session.get(OrderRecord, order_id)
        return self._to_domain(record) if record else None

    def get_for_update(self, order_id: int) -> Order | None:
        record = self.session.get(OrderRecord, order_id, with_for_update=True)       # bayar vs batal bergantian
        return self._to_domain(record) if record else None

    def best_sellers(self, limit: int) -> list[dict]:
        sold = func.sum(OrderLineRecord.qty).label("sold")
        rows = self.session.execute(
            select(OrderLineRecord.product_id, OrderLineRecord.product, sold)
            .join(OrderRecord, OrderRecord.id == OrderLineRecord.order_id)
            .where(OrderRecord.status == OrderStatus.PAID.value)         # hanya order yang sudah dibayar
            .group_by(OrderLineRecord.product_id, OrderLineRecord.product)
            .order_by(sold.desc(), OrderLineRecord.product_id)
            .limit(limit)
        )
        return [{"product_id": r.product_id, "name": r.product, "sold": int(r.sold)} for r in rows]

    def list_for_customer(self, customer: str, limit: int, after: int | None = None) -> list[Order]:
        query = (select(OrderRecord)
                 .options(selectinload(OrderRecord.lines))       # item semua order dalam 1 query
                 .where(OrderRecord.customer == customer)
                 .order_by(OrderRecord.id.desc())
                 .limit(limit))
        if after is not None:
            query = query.where(OrderRecord.id < after)          # keyset: lanjut setelah id terakhir
        return [self._to_domain(r) for r in self.session.scalars(query)]

    def sales_summary(self) -> dict:
        # total order = subtotal - diskon, sama seperti Order.total di domain, tapi dihitung di database
        subtotals = (select(OrderLineRecord.order_id,
                            func.sum(OrderLineRecord.price * OrderLineRecord.qty).label("subtotal"))
                     .group_by(OrderLineRecord.order_id)
                     .subquery())
        paid = OrderRecord.status == OrderStatus.PAID.value
        row = self.session.execute(
            select(func.count(),
                   func.count().filter(paid),
                   func.count().filter(OrderRecord.status == OrderStatus.CANCELLED.value),
                   func.sum(subtotals.c.subtotal - OrderRecord.discount).filter(paid))
            .select_from(OrderRecord)
            .outerjoin(subtotals, subtotals.c.order_id == OrderRecord.id)
        ).one()
        return {"total_orders": row[0], "paid_orders": row[1], "cancelled_orders": row[2],
                "revenue": int(row[3] or 0)}

    def save(self, order: Order) -> None:
        # setelah dibuat, yang bisa berubah dari order cuma status-nya
        self.session.get(OrderRecord, order.id).status = order.status.value
        self.status_changed = True

    @staticmethod
    def _to_domain(record: OrderRecord) -> Order:
        lines = [OrderLine(line.product_id, line.product, Money(line.price), line.qty) for line in record.lines]
        return Order(record.customer, record.customer_type, id=record.id, status=OrderStatus(record.status),
                     lines=lines, discount=Money(record.discount), voucher_code=record.voucher_code)


class SqlAlchemyVoucherRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, voucher: Voucher) -> Voucher:
        self.session.add(VoucherRecord(code=voucher.code, amount=voucher.amount.amount, quota=voucher.quota))
        self.session.flush()
        return voucher

    def get(self, code: str) -> Voucher | None:
        record = self.session.get(VoucherRecord, code)
        return Voucher(record.code, Money(record.amount), record.quota) if record else None

    def get_for_update(self, code: str) -> Voucher | None:
        record = self.session.get(VoucherRecord, code, with_for_update=True)         # kunci baris sampai commit
        return Voucher(record.code, Money(record.amount), record.quota) if record else None

    def save(self, voucher: Voucher) -> None:
        self.session.get(VoucherRecord, voucher.code).quota = voucher.quota


class SqlAlchemyUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, user: User) -> User:
        record = UserRecord(email=user.email, password_hash=user.password_hash, role=user.role,
                            customer_type=user.customer_type)
        self.session.add(record)
        self.session.flush()
        user.id = record.id
        return user

    def get_by_email(self, email: str) -> User | None:
        record = self.session.scalar(select(UserRecord).where(UserRecord.email == email))
        if record is None:
            return None
        return User(record.email, record.password_hash, record.role, record.customer_type, id=record.id)
