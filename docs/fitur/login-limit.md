# Fitur: Batas Login Gagal

Mencegah tebak password (brute force) di `POST /auth/token`. Login gagal dihitung **per email** di Redis.

## Aturan bisnis

- Gagal ke-5 dalam 15 menit: login berikutnya dijawab `429 too_many_login_attempts` + header `Retry-After`, **walaupun password benar**
- Login berhasil mereset hitungan
- Email yang tidak terdaftar ikut dihitung (penyerang tidak bisa membedakan email terdaftar dan tidak)
- Email lain tidak ikut diblokir. `Budi@Mail.com` dan `budi@mail.com` dianggap satu email
- Log login gagal berisi email dan jumlah gagal, tanpa password
- Setting: `LOGIN_MAX_ATTEMPTS` (default 5) dan `LOGIN_BLOCK_SECONDS` (default 900)

## Endpoint

| Method | Path | Keterangan |
|---|---|---|
| POST | `/auth/token` | Login. Sekarang bisa menjawab 429 |

## Error

| Code | HTTP | Kapan |
|---|---|---|
| `invalid_credentials` | 401 | Email atau password salah (hitungan bertambah) |
| `too_many_login_attempts` | 429 | Sudah gagal terlalu sering, ada `Retry-After` (detik) |

## Observability

- Log JSON: `login gagal` (WARNING) berisi `email` dan `failures`, `login diblokir sementara`
- Metric: `login_failures_total`, `login_blocked_total` di `/metrics`
- Alert Prometheus `LoginBruteForceSuspected`: lebih dari 20 login gagal dalam 5 menit

## File

| Layer | File | Perubahan |
|---|---|---|
| application | `ports.py`, `errors.py`, `auth_service.py` | Port `LoginAttemptLimiter`, error `TooManyLoginAttempts`, `AuthService.login` cek blokir, catat gagal, reset |
| infrastructure | `login_limiter.py`, `metrics.py`, `config.py` | `RedisLoginAttemptLimiter` (INCR + EXPIRE NX), metric, setting |
| api | `dependencies.py`, `errors.py`, `routers/auth.py` | `get_login_limiter`, handler 429 + `Retry-After` |

## Keputusan teknis

Lihat [ADR 0007](../adr/0007-batas-login-gagal-per-email.md), termasuk risiko orang lain mengunci email korban.

## Test

```bash
pytest tests/test_login_limit.py -q
```

Yang dites: gagal ke-6 ditolak walau password benar, login berhasil mereset, email tidak terdaftar ikut dihitung,
email lain tidak ikut diblokir, log tanpa password, metric bertambah, dan use case tanpa Redis (limiter palsu).
