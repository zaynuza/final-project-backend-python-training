# ADR 0001: Kode dipisah per layer (domain, application, infrastructure, api)

Tanggal: 2026-10-16
Status: Diterima

## Konteks

Versi awal Order API ditulis di satu file: route, aturan diskon, dan query
database bercampur. Mengubah aturan diskon berisiko merusak endpoint, dan
business logic tidak bisa dites tanpa database.

## Keputusan

Kode dipisah menjadi empat layer. `domain` berisi aturan bisnis tanpa library
luar, `application` berisi use case dan port (interface), `infrastructure`
berisi adapter (SQLAlchemy, Redis, RabbitMQ), dan `api` berisi FastAPI.
Dependency hanya mengarah ke dalam.

## Konsekuensi

- Business logic dites dengan fake adapter, tanpa database (`tests/fakes.py`)
- Mengganti teknologi (misalnya Celery ke RabbitMQ) cukup mengganti adapter
- Jumlah file lebih banyak, dan developer baru perlu memahami arah dependency
