# ADR 0007: Batas login gagal per email dengan counter Redis

Tanggal: 2026-11-06
Status: Diterima

## Konteks

`POST /auth/token` bisa dipanggil tanpa batas. Penyerang bisa mencoba ribuan password untuk satu email (brute force),
dan tim tidak tahu sedang diserang. Rate limit global per IP (Sesi 6) tidak cukup: penyerang bisa berganti IP,
dan endpoint login tidak memakainya.

## Keputusan

- Login gagal dihitung per email di Redis: `INCR login-fail:<email>` dengan `EXPIRE ... NX` (15 menit sejak gagal pertama)
- Gagal ke-5 (`LOGIN_MAX_ATTEMPTS`): login berikutnya dijawab `429 too_many_login_attempts` + `Retry-After`,
  walaupun password benar. Pengecekan dilakukan SEBELUM password diperiksa
- Login berhasil menghapus counter. Email yang tidak terdaftar ikut dihitung, supaya penyerang tidak bisa membedakan
  email terdaftar dan tidak dari perilaku sistem. Email dinormalkan ke huruf kecil
- Port `LoginAttemptLimiter` ada di application, adapter `RedisLoginAttemptLimiter` di infrastructure.
  `domain/` dan `application/` tetap tanpa import redis dan prometheus_client
- Log berisi email dan jumlah gagal, tanpa password. Metric `login_failures_total` dan `login_blocked_total`,
  alert `LoginBruteForceSuspected` (Prometheus) menyala jika lebih dari 20 login gagal dalam 5 menit

## Konsekuensi

- Pihak lain bisa sengaja mengunci email korban selama 15 menit (*lockout DoS*). Penanganan lanjutan:
  batas per IP di API gateway, CAPTCHA, atau notifikasi ke pemilik akun
- Redis mati = login gagal dengan 503 (*fail closed*), lebih aman daripada membuka login tanpa batas
- Counter punya masa berlaku sendiri, tidak ada yang perlu dibersihkan manual

## Alternatif yang dipertimbangkan

- Batas per IP saja: gagal melawan penyerang dengan banyak IP, dan merugikan banyak pengguna di balik satu IP (kantor, kampus)
- Kolom `failed_attempts` di tabel users: sebuah write ke database di setiap login gagal, dan tidak kedaluwarsa otomatis
- Penundaan yang membesar (*exponential backoff*) tanpa blokir: lebih halus untuk pengguna sah, lebih rumit dites
