"""API: autentikasi OAuth2 Bearer + otorisasi berbasis scope.

Endpoint menyatakan scope yang dibutuhkan:
    user: CurrentUser = Security(get_current_user, scopes=["products:write"])
FastAPI mengumpulkan scope itu ke SecurityScopes, lalu get_current_user:
1. membaca header Authorization: Bearer <token> (OAuth2PasswordBearer)
2. meminta AuthService membaca token dan mengecek scope
Tidak ada token / token salah = 401. Token benar tapi scope kurang = 403.
"""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from app.api.dependencies import get_auth_service
from app.application.auth_service import AuthService, CurrentUser
from app.application.errors import InvalidToken

SCOPES = {
    "orders:write": "Membuat dan mengelola order sendiri",
    "orders:all": "Melihat dan mengelola order semua customer",
    "products:write": "Menambah dan mengubah produk",
    "reports:read": "Melihat report penjualan",
}
# auto_error=False: token kosong ditangani sendiri, supaya format error-nya sama dengan error lain
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", scopes=SCOPES, auto_error=False)


def get_current_user(security_scopes: SecurityScopes, token: str | None = Depends(oauth2_scheme),
                     auth: AuthService = Depends(get_auth_service)) -> CurrentUser:
    if not token:
        raise InvalidToken("Butuh login: kirim header Authorization: Bearer <token>")
    return auth.authenticate(token, security_scopes.scopes)
