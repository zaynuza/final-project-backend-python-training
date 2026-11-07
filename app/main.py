"""Order API - final project: order, voucher, produk terlaris, poin loyalty, report, notifikasi.

Butuh JWT_SECRET (minimal 32 karakter) di environment atau file .env, lihat .env.example.

Jalankan semua service dalam container dari folder final-project/:
    cp .env.example .env                                   isi JWT_SECRET
    docker compose up -d --build                           API, worker, consumer, dan dependency-nya
    docker compose exec api python create_user.py admin@toko.com --role admin

Di Kubernetes: kubectl apply -f k8s/ (lihat README). Tanpa container, cara Sesi 10 tetap bisa dipakai.

Lihat hasilnya:
    http://localhost:8000/metrics        metrics Prometheus
    http://localhost:8000/health/ready   readiness check
    http://localhost:16686               trace di Jaeger
    http://localhost:9090                Prometheus (grafik dan alert)

Isi data dan ukur performa query:
    python seed.py                         isi PostgreSQL dengan 20.000 order
    python profile_queries.py --explain    ukur waktu, jumlah query, dan EXPLAIN ANALYZE
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import observe_requests
from app.api.routers import auth, customers, ops, orders, products, reports, vouchers
from app.infrastructure.config import check_api_settings, get_settings
from app.infrastructure.logs import setup_logging
from app.infrastructure.tracing import setup_tracing

settings = get_settings()
check_api_settings(settings)                     # JWT_SECRET tidak ada = API gagal start
setup_logging(settings.log_level)
docs = settings.env == "development"             # /docs hanya di development

app = FastAPI(
    title="Order Payment API",
    version="1.0.0",
    description="API toko online: produk, order, voucher, poin loyalty, report penjualan, dan notifikasi event-driven.",
    openapi_tags=[
        {"name": "products", "description": "Data produk dan stok (di-cache di Redis)"},
        {"name": "orders",
         "description": "Membuat, membayar, membatalkan, dan melihat riwayat order (dibatasi rate limit)"},
        {"name": "vouchers", "description": "Voucher belanja dengan kuota (admin)"},
        {"name": "customers", "description": "Saldo poin loyalty customer dari event order.paid"},
        {"name": "reports", "description": "Report penjualan, dibuat di background oleh worker"},
        {"name": "ops", "description": "Health check dan metrics untuk monitoring"},
        {"name": "auth", "description": "Login OAuth2 (password flow), menghasilkan JWT"},
    ],
    docs_url="/docs" if docs else None, redoc_url=None, openapi_url="/openapi.json" if docs else None,
)

app.middleware("http")(observe_requests)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,      # kosong = tidak ada
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
register_exception_handlers(app)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(vouchers.router)
app.include_router(customers.router)
app.include_router(reports.router)
app.include_router(ops.router)
app.include_router(auth.router)
setup_tracing("order-api", app)
