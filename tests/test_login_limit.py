"""Test pembatas login gagal (studi kasus Sesi 10): blokir, reset, email tidak terdaftar, log tanpa password."""
import logging

import pytest
from prometheus_client import REGISTRY

from app.application.auth_service import AuthService
from app.application.errors import InvalidCredentials, TooManyLoginAttempts
from app.domain.user import User
from tests.conftest import PASSWORD
from tests.fakes import FakeUnitOfWork

SALAH = "password-salah-rahasia"
RETRY_AFTER_MAKS = 900                                   # LOGIN_BLOCK_SECONDS default (15 menit)


def login(client, email="budi@mail.com", password=PASSWORD):
    return client.post("/auth/token", data={"username": email, "password": password})


def gagal(client, kali, email="budi@mail.com"):
    return [login(client, email, SALAH).status_code for _ in range(kali)]


def test_gagal_lima_kali_login_keenam_ditolak_walau_password_benar(client):
    assert gagal(client, 5) == [401] * 5                  # lima kali pertama masih dijawab "salah"
    blocked = login(client, password=PASSWORD)            # keenam: password benar, tetap ditolak
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_login_attempts"
    assert 0 < int(blocked.headers["Retry-After"]) <= RETRY_AFTER_MAKS


def test_login_berhasil_mereset_hitungan(client):
    gagal(client, 4)
    assert login(client).status_code == 200               # berhasil sebelum kena batas
    assert gagal(client, 4) == [401] * 4                  # hitungan mulai dari nol lagi, belum diblokir
    assert login(client).status_code == 200


def test_email_tidak_terdaftar_ikut_dihitung(client):
    gagal(client, 5, email="tidakada@mail.com")
    assert login(client, "tidakada@mail.com").status_code == 429


def test_email_lain_tidak_ikut_diblokir(client):
    gagal(client, 5, email="budi@mail.com")
    assert login(client, "budi@mail.com").status_code == 429
    assert login(client, "ani@mail.com").status_code == 200


def test_huruf_besar_kecil_dianggap_email_yang_sama(client):
    gagal(client, 5, email="Budi@Mail.com")
    assert login(client, "budi@mail.com").status_code == 429


def test_hitungan_punya_masa_berlaku(client, fake_redis):
    gagal(client, 2)
    assert 0 < fake_redis.ttl("login-fail:budi@mail.com") <= RETRY_AFTER_MAKS


def test_log_login_gagal_berisi_email_tanpa_password(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.security"):
        gagal(client, 2)
    records = [r for r in caplog.records if r.name == "app.security"]
    assert [r.failures for r in records] == [1, 2]
    assert all(r.email == "budi@mail.com" for r in records)
    semua_teks = " ".join(f"{r.getMessage()} {vars(r)}" for r in records)
    assert SALAH not in semua_teks and PASSWORD not in semua_teks


def test_metric_login_failures_total_bertambah(client):
    sebelum = REGISTRY.get_sample_value("login_failures_total") or 0
    gagal(client, 3)
    assert REGISTRY.get_sample_value("login_failures_total") == sebelum + 3
    assert "login_failures_total" in client.get("/metrics").text


# ---------- use case tanpa Redis: limiter palsu lewat port ----------
class FakeLimiter:
    def __init__(self):
        self.failures: list[str] = []
        self.resets: list[str] = []
        self.blocked = 0

    def retry_after(self, email):
        return self.blocked

    def record_failure(self, email):
        self.failures.append(email)

    def reset(self, email):
        self.resets.append(email)


class PlainHasher:
    def hash(self, password):
        return "hash:" + password

    def verify(self, password, password_hash):
        return password_hash == "hash:" + password


class StubTokens:
    def issue(self, user):
        return "token-" + user.email


@pytest.fixture
def auth_service():
    uow = FakeUnitOfWork()
    uow.users.add(User("budi@mail.com", "hash:benar", "customer", "vip"))
    limiter = FakeLimiter()
    return AuthService(uow, PlainHasher(), StubTokens(), limiter), limiter


def test_use_case_mencatat_gagal_dan_mereset_saat_berhasil(auth_service):
    service, limiter = auth_service
    with pytest.raises(InvalidCredentials):
        service.login("budi@mail.com", "salah")
    assert limiter.failures == ["budi@mail.com"]
    assert service.login("budi@mail.com", "benar") == "token-budi@mail.com"
    assert limiter.resets == ["budi@mail.com"]


def test_use_case_menolak_sebelum_cek_password_kalau_diblokir(auth_service):
    service, limiter = auth_service
    limiter.blocked = 600
    with pytest.raises(TooManyLoginAttempts) as error:
        service.login("budi@mail.com", "benar")
    assert error.value.retry_after == 600
    assert limiter.failures == [] and limiter.resets == []        # password tidak dicek dan tidak dihitung
