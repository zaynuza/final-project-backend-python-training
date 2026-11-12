"""Infrastructure: pembatas login gagal per email dengan Redis (adapter untuk port LoginAttemptLimiter).

Setiap login gagal menaikkan counter `login-fail:<email>` (INCR). Counter kedaluwarsa sendiri setelah
`block_seconds` sejak gagal pertama (EXPIRE NX), jadi tidak ada yang perlu dibersihkan manual.
Counter >= max_attempts berarti diblokir sampai counter kedaluwarsa. Login berhasil menghapus counter.

Log berisi email dan jumlah gagal, tidak pernah password. Metric: login_failures_total, login_blocked_total.

Catatan desain:
- Dihitung per email, bukan per IP: penyerang yang memakai banyak IP tetap kena batas.
  Konsekuensinya orang lain bisa sengaja mengunci email korban selama 15 menit. Kalau itu jadi masalah,
  tambahkan batas per IP juga (rate limit di api gateway) dan jangan bergantung pada satu lapisan saja.
- Redis mati = login gagal dengan 503 (fail closed). Lebih aman daripada membuka login tanpa batas.
"""
import logging

from redis import Redis

from app.infrastructure.metrics import LOGIN_BLOCKED, LOGIN_FAILURES

logger = logging.getLogger("app.security")


class RedisLoginAttemptLimiter:
    def __init__(self, redis: Redis, max_attempts: int, block_seconds: int):
        self.redis = redis
        self.max_attempts = max_attempts
        self.block_seconds = block_seconds

    @staticmethod
    def _key(email: str) -> str:
        return f"login-fail:{email.strip().lower()}"             # Budi@Mail.com dan budi@mail.com = satu orang

    def retry_after(self, email: str) -> int:
        key = self._key(email)
        failures = int(self.redis.get(key) or 0)
        if failures < self.max_attempts:
            return 0
        LOGIN_BLOCKED.inc()
        logger.warning("login diblokir sementara", extra={
            "email": email, "failures": failures, "error_type": "client"})
        return max(1, self.redis.ttl(key))

    def record_failure(self, email: str) -> None:
        key = self._key(email)
        pipe = self.redis.pipeline()                              # INCR + EXPIRE dalam satu transaksi Redis
        pipe.incr(key)
        pipe.expire(key, self.block_seconds, nx=True)             # jam mulai dari gagal pertama, tidak diperpanjang
        failures, _ = pipe.execute()
        LOGIN_FAILURES.inc()
        logger.warning("login gagal", extra={"email": email, "failures": failures, "error_type": "client"})

    def reset(self, email: str) -> None:
        self.redis.delete(self._key(email))
