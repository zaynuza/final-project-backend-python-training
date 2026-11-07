# Deployment Readiness Checklist

Dicek sebelum versi baru dirilis ke production. Semua harus terpenuhi.

## Kode dan test

- [ ] Pull request sudah di-review minimal satu orang
- [ ] Pipeline CI hijau: lint, test (termasuk `test_concurrency` di PostgreSQL), build, scan image
- [ ] Tidak ada temuan HIGH atau CRITICAL dari Trivy

## Konfigurasi

- [ ] `ENV=production`, `/docs` mati
- [ ] `JWT_SECRET` dan `DATABASE_URL` dari Secret, bukan dari file di repository. `.env` tidak ada di git (cek `.gitignore`)
- [ ] Secret yang pernah tertulis di file yang ikut ter-commit sudah diganti (rotasi), bukan hanya dihapus dari file
- [ ] `LOGIN_MAX_ATTEMPTS` dan `LOGIN_BLOCK_SECONDS` sesuai kebijakan keamanan
- [ ] `CORS_ORIGINS` hanya domain frontend
- [ ] Batas resource (CPU, memori) di manifest Kubernetes sudah diisi

## Data

- [ ] Perubahan tabel sudah diuji di staging, dan bisa dijalankan tanpa menghentikan API. Aplikasi ini membuat tabel dengan `create_all`
      (tidak mengubah tabel yang sudah ada), jadi kolom baru (misalnya `orders.voucher_code`) harus ditambah lewat migrasi (Alembic) atau `ALTER TABLE`
- [ ] Backup database terakhir berhasil

## Observability

- [ ] Readiness dan liveness probe aktif
- [ ] Metrics terbaca di Prometheus (API, consumer notifikasi, consumer poin), alert SLO dan `EventPublishFailed` aktif
- [ ] Log JSON terbaca, `request_id` dan `trace_id` ada

## Setelah deploy

- [ ] Smoke test lulus
- [ ] Error rate dan latency di dashboard normal selama 15 menit
- [ ] Cara rollback diketahui: `kubectl rollout undo deploy/order-api`
