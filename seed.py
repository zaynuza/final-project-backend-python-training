"""Isi database aplikasi (PostgreSQL) dengan data yang cukup banyak untuk profiling.

Perhatian: semua tabel aplikasi dihapus lalu dibuat ulang dari model (user, produk, voucher, order ikut hilang).
Jangan jalankan di database yang dipakai demo. Pakai database terpisah, misalnya orders_perf:
    docker compose exec postgres createdb -U app orders_perf
    docker compose exec -e DATABASE_URL=postgresql+psycopg://app:app@postgres:5432/orders_perf api python seed.py
Isinya 100 produk dan 20.000 order dari 1.000 customer, masing-masing 2 item.
Cache produk di Redis ikut dikosongkan, supaya tidak menampilkan data lama.

Butuh PostgreSQL + Redis: docker compose up -d (dari folder final-project)
Jalankan: python seed.py (atau lewat container, lihat di atas)
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/orders")

from sqlalchemy import text  # noqa: E402

from app.infrastructure.database import Base, get_session_factory  # noqa: E402
from app.infrastructure.redis_client import get_redis  # noqa: E402

SEED = """
INSERT INTO products (name, price, stock)
SELECT 'Produk ' || g, 10000 + (g * 7919) % 990000, 1000
FROM generate_series(1, 100) AS g;

INSERT INTO orders (customer, customer_type, status, discount)
SELECT 'customer' || (g % 1000) || '@mail.com', 'regular',
       (ARRAY['pending', 'paid', 'paid', 'cancelled'])[1 + g % 4], 0
FROM generate_series(1, 20000) AS g;

INSERT INTO order_lines (order_id, product_id, product, price, qty)
SELECT o.id, p.id, p.name, p.price, 1 + (o.id + n) % 3
FROM orders AS o
CROSS JOIN generate_series(1, 2) AS n
JOIN products AS p ON p.id = 1 + (o.id * 7 + n) % 100;

ANALYZE;
"""

if __name__ == "__main__":
    engine = get_session_factory().kw["bind"]
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)              # tabel + index sesuai model
    with engine.begin() as conn:
        conn.execute(text(SEED))
        orders = conn.execute(text("SELECT count(*) FROM orders")).scalar()
    get_redis().flushdb()
    print(f"{orders} order siap di {engine.url.render_as_string(hide_password=True)}")
