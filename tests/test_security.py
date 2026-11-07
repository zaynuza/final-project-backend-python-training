"""Test keamanan: login, token, scope (RBAC), kepemilikan order, validasi input, dan setting."""
import dataclasses

import jwt
import pytest

from app.infrastructure.config import check_api_settings, get_settings
from app.infrastructure.database import get_session_factory
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.conftest import PASSWORD, auth, order


def login(client, email, password):
    return client.post("/auth/token", data={"username": email, "password": password})


# ---------------------------------------------------------------- login dan token
def test_login_benar_mendapat_token_dan_scope(client):
    response = login(client, "budi@mail.com", PASSWORD)
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me == {"email": "budi@mail.com", "role": "customer", "customer_type": "vip",
                  "scopes": ["orders:write"]}


@pytest.mark.parametrize("email, password", [("budi@mail.com", "salah"), ("tidakada@mail.com", PASSWORD)])
def test_login_salah_pesannya_sama(client, email, password):
    response = login(client, email, password)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email atau password salah"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_password_disimpan_sebagai_hash():
    with SqlAlchemyUnitOfWork(get_session_factory()) as uow:
        user = uow.users.get_by_email("budi@mail.com")
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_tanpa_token_401(client):
    client.headers.pop("Authorization")
    response = client.post("/orders", json=order((1, 1)))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_token_kedaluwarsa_401(client):
    response = client.post("/orders", json=order((1, 1)), headers=auth("budi@mail.com", minutes=-1))
    assert response.status_code == 401
    assert "kedaluwarsa" in response.json()["error"]["message"]


def test_token_diubah_jadi_admin_ditolak(client):
    token = auth("budi@mail.com")["Authorization"].split()[1]
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["scope"] = "orders:write orders:all products:write reports:read"
    forged = jwt.encode(claims, "secret-penyerang-yang-juga-panjang-32-karakter", algorithm="HS256")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


# ---------------------------------------------------------------- scope (RBAC)
def test_customer_tidak_bisa_tambah_produk(client):
    response = client.post("/products", json={"name": "Monitor", "price": 2_000_000, "stock": 3})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_bisa_tambah_produk(client):
    response = client.post("/products", json={"name": "Monitor", "price": 2_000_000, "stock": 3},
                           headers=auth("admin@toko.com"))
    assert response.status_code == 201


def test_customer_tidak_bisa_lihat_report(client):
    assert client.post("/reports/sales").status_code == 403


def test_produk_tetap_bisa_dilihat_tanpa_login(client):
    client.headers.pop("Authorization")
    assert client.get("/products").status_code == 200


# ---------------------------------------------------------------- kepemilikan order
def test_order_atas_nama_user_di_token(client):
    created = client.post("/orders", json=order((1, 2))).json()
    assert created["customer"] == "budi@mail.com"
    assert created["customer_type"] == "vip"              # dari data user, bukan dari body
    assert created["total"] == 900_000


def test_customer_dan_diskon_tidak_bisa_dikirim_lewat_body(client):
    body = {**order((1, 2)), "customer": "ani@mail.com", "customer_type": "vip"}
    response = client.post("/orders", json=body)
    assert response.status_code == 422


def test_customer_lain_tidak_bisa_akses_order(client):
    order_id = client.post("/orders", json=order((1, 1))).json()["id"]
    ani = auth("ani@mail.com")
    for method, path in [("GET", f"/orders/{order_id}"), ("POST", f"/orders/{order_id}/pay"),
                         ("POST", f"/orders/{order_id}/cancel")]:
        response = client.request(method, path, headers=ani)
        assert response.status_code == 404                # sama seperti order yang tidak ada
    assert client.get(f"/orders/{order_id}", headers=auth("admin@toko.com")).status_code == 200


def test_riwayat_order_customer_lain_hanya_untuk_admin(client):
    client.post("/orders", json=order((1, 1)))
    params = {"customer": "budi@mail.com"}
    assert client.get("/orders", params=params, headers=auth("ani@mail.com")).status_code == 403
    admin_view = client.get("/orders", params=params, headers=auth("admin@toko.com")).json()
    assert len(admin_view["items"]) == 1


# ---------------------------------------------------------------- input dan setting
def test_qty_terlalu_besar_ditolak(client):
    response = client.post("/orders", json=order((1, 1000)))
    assert response.status_code == 422


def test_api_tidak_mau_start_tanpa_jwt_secret():
    insecure = dataclasses.replace(get_settings(), jwt_secret="pendek")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        check_api_settings(insecure)


def test_secret_tidak_tercetak():
    assert get_settings().jwt_secret not in repr(get_settings())
