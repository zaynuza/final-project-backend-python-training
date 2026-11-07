"""API: login (OAuth2 password flow) dan data user yang sedang login.

POST /auth/token menerima form (bukan JSON) berisi username dan password, sesuai standar OAuth2.
Karena itu tombol Authorize di /docs bisa langsung dipakai untuk login.
username diisi email.
Login gagal dihitung per email. Gagal ke-5 dalam 15 menit: login berikutnya 429 + Retry-After, walau password benar.
"""
from fastapi import APIRouter, Depends, Security
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import get_auth_service
from app.api.schemas import ErrorOut, MeOut, TokenOut
from app.api.security import get_current_user
from app.application.auth_service import AuthService, CurrentUser
from app.infrastructure.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
UNAUTHORIZED = {401: {"model": ErrorOut, "description": "Email/password salah atau token tidak valid"}}


@router.post("/token", response_model=TokenOut, summary="Login, mendapatkan access token",
             responses={**UNAUTHORIZED,
                        429: {"model": ErrorOut, "description": "Terlalu banyak login gagal (lihat Retry-After)"}})
def login(form: OAuth2PasswordRequestForm = Depends(), auth: AuthService = Depends(get_auth_service)):
    token = auth.login(form.username, form.password)
    return TokenOut(access_token=token, expires_in=get_settings().access_token_minutes * 60)


@router.get("/me", response_model=MeOut, summary="User yang sedang login", responses=UNAUTHORIZED)
def me(user: CurrentUser = Security(get_current_user)):
    return MeOut(email=user.email, role=user.role, customer_type=user.customer_type,
                 scopes=sorted(user.scopes))
