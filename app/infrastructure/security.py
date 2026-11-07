"""Infrastructure: adapter untuk port PasswordHasher dan TokenService.

- Argon2PasswordHasher : hash password dengan Argon2 (pwdlib), algoritma yang sengaja lambat dan butuh memori,
                         supaya menebak password dari hash yang bocor sangat mahal
- JwtTokenService      : JWT HS256 berisi sub, role, customer_type, scope, iat, exp
Claim "scope" ditulis sebagai teks dipisah spasi, sesuai standar OAuth2.
"""
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.application.errors import InvalidToken
from app.domain.user import User


class Argon2PasswordHasher:
    def __init__(self):
        self.hasher = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self.hasher.verify(password, password_hash)


class JwtTokenService:
    ALGORITHM = "HS256"

    def __init__(self, secret: str, minutes: int):
        self.secret = secret
        self.minutes = minutes

    def issue(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        claims = {"sub": user.email, "role": user.role, "customer_type": user.customer_type,
                  "scope": " ".join(sorted(user.scopes)),
                  "iat": now, "exp": now + timedelta(minutes=self.minutes)}
        return jwt.encode(claims, self.secret, algorithm=self.ALGORITHM)

    def read(self, token: str) -> dict:
        try:
            # algorithms wajib ditulis, supaya token dengan algoritma lain (misalnya "none") ditolak
            return jwt.decode(token, self.secret, algorithms=[self.ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise InvalidToken("Token kedaluwarsa, silakan login lagi") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidToken("Token tidak valid") from exc
