"""Infrastructure: metrics Prometheus.

Tiga angka utama (RED): Rate (jumlah request), Errors (status 5xx), Duration (waktu response).
Ditambah metrics bisnis: event yang dikirim, notifikasi yang diproses consumer, dan login gagal (tanda brute force).
API menampilkan metrics di GET /metrics, consumer di port terpisah (CONSUMER_METRICS_PORT).
"""
from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "Jumlah request HTTP",
    ["method", "route", "status"])

HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "Waktu response HTTP",
    ["method", "route"],
    buckets=[0.01, 0.05, 0.1, 0.3, 0.5, 1, 2.5])         # 0.3 = batas SLO latency

EVENTS_PUBLISHED = Counter(
    "events_published_total", "Event yang dikirim ke RabbitMQ",
    ["type", "result"])                                  # result: ok / failed

NOTIFICATIONS = Counter(
    "notifications_processed_total", "Event yang diproses consumer notifikasi",
    ["result"])                                          # sent / skipped / retrying / dead_lettered

LOGIN_FAILURES = Counter(
    "login_failures_total", "Login gagal (password salah atau email tidak terdaftar)")

LOGIN_BLOCKED = Counter(
    "login_blocked_total", "Login ditolak karena email sudah terlalu sering gagal")

POINT_EVENTS = Counter(
    "points_events_processed_total", "Event yang diproses consumer poin loyalty",
    ["result"])                                          # added / skipped / ignored / dead_lettered
