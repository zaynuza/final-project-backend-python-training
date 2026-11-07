"""Membuat user baru dari terminal, misalnya admin pertama.

Password ditanyakan lewat getpass (tidak tampil di layar dan tidak tersimpan di history terminal).
Untuk script otomatis, password bisa dikirim lewat environment variable NEW_USER_PASSWORD.

Jalankan dari folder starter/:
    python create_user.py admin@toko.com --role admin
    python create_user.py budi@mail.com --type vip
"""
import argparse
import getpass
import os

from app.application.auth_service import AuthService
from app.application.errors import UserAlreadyExists
from app.infrastructure.config import get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork


def main() -> None:
    parser = argparse.ArgumentParser(description="Buat user Order API")
    parser.add_argument("email")
    parser.add_argument("--role", choices=["customer", "admin"], default="customer")
    parser.add_argument("--type", dest="customer_type", choices=["regular", "member", "vip"], default="regular")
    args = parser.parse_args()

    password = os.getenv("NEW_USER_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 8:
        raise SystemExit("Password minimal 8 karakter")

    settings = get_settings()
    auth = AuthService(SqlAlchemyUnitOfWork(get_session_factory()), Argon2PasswordHasher(),
                       JwtTokenService(settings.jwt_secret, settings.access_token_minutes))
    try:
        user = auth.register(args.email, password, args.role, args.customer_type)
    except UserAlreadyExists as exc:
        raise SystemExit(str(exc))
    print(f"User dibuat: {user.email} (role {user.role}, {user.customer_type})")


if __name__ == "__main__":
    main()
