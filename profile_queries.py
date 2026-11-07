"""Ukur performa query aplikasi: waktu dan jumlah query ke database.

Jumlah query dihitung lewat event SQLAlchemy "before_cursor_execute",
yang terpanggil setiap kali ada SQL dikirim ke database.

Jalankan seed.py dulu (isi 20.000 order), lalu:
    python profile_queries.py             waktu dan jumlah query
    python profile_queries.py --explain   + EXPLAIN ANALYZE: rencana query yang sebenarnya dijalankan PostgreSQL

Cara membaca EXPLAIN ANALYZE:
- "Index Scan" / "Index Only Scan" = memakai index (cepat). "Seq Scan" = membaca seluruh tabel (lambat di tabel besar)
- "actual time" = waktu sebenarnya (ms), "rows" = jumlah baris, "Execution Time" = total
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/orders")
os.environ.setdefault("QUERY_DELAY", "0")         # matikan simulasi query lambat dari Sesi 6

import statistics  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

from sqlalchemy import event, text  # noqa: E402

from app.application.report_service import ReportService  # noqa: E402
from app.infrastructure.database import get_session_factory  # noqa: E402
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork  # noqa: E402

session_factory = get_session_factory()
queries = 0


@event.listens_for(session_factory.kw["bind"], "before_cursor_execute")
def count_query(*args):
    global queries
    queries += 1


def measure(fn) -> tuple[float, int]:
    global queries
    queries = 0
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000, queries


def order_detail() -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        uow.orders.get(12345)


EXPLAIN_QUERIES = {
    "Detail order (primary key)": "SELECT * FROM orders WHERE id = 12345",
    "Riwayat order customer (index customer, id)":
        "SELECT * FROM orders WHERE customer = 'customer7@mail.com' ORDER BY id DESC LIMIT 20",
    "Item order (index order_id)": "SELECT * FROM order_lines WHERE order_id = 12345",
    "Produk terlaris (GROUP BY di database)":
        "SELECT l.product_id, l.product, SUM(l.qty) AS sold FROM order_lines l JOIN orders o ON o.id = l.order_id "
        "WHERE o.status = 'paid' GROUP BY l.product_id, l.product ORDER BY sold DESC, l.product_id LIMIT 10",
}


def explain_analyze() -> None:
    """Jalankan EXPLAIN ANALYZE untuk query penting. Query benar-benar dieksekusi, hasilnya dibuang."""
    with session_factory() as session:
        for title, sql in EXPLAIN_QUERIES.items():
            print(f"\n== {title}\n   {sql[:100]}")
            for line in session.execute(text("EXPLAIN ANALYZE " + sql)).scalars():
                print("   " + line)


if __name__ == "__main__":
    report_ms, report_queries = measure(ReportService(SqlAlchemyUnitOfWork(session_factory)).sales_summary)
    details = [measure(order_detail) for _ in range(50)]

    print(f"Report penjualan       : {report_ms:8.1f} ms, {report_queries} query")
    print(f"Detail order (median)  : {statistics.median(ms for ms, _ in details):8.1f} ms, {details[0][1]} query")
    if "--explain" in sys.argv:
        explain_analyze()
