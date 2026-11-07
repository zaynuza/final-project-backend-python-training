"""Smoke test juga dites, supaya script-nya tidak rusak saat API berubah.

TestClient adalah httpx.Client, jadi run() bisa dipanggil langsung tanpa server.
"""
from app.api.dependencies import get_health_checks
from app.main import app
from smoke_test import run
from tests.conftest import PASSWORD


def test_smoke_test_lulus_jika_semua_sehat(client, capsys):
    app.dependency_overrides[get_health_checks] = lambda: {"database": lambda: None}
    client.headers.pop("Authorization")
    assert run(client, "admin@toko.com", PASSWORD)
    assert "GAGAL" not in capsys.readouterr().out


def test_smoke_test_gagal_jika_dependency_mati(client, capsys):
    def down():
        raise ConnectionError("RabbitMQ mati")

    app.dependency_overrides[get_health_checks] = lambda: {"rabbitmq": down}
    client.headers.pop("Authorization")
    assert not run(client, "admin@toko.com", PASSWORD)
    assert "GAGAL semua dependency siap" in capsys.readouterr().out


def test_smoke_test_gagal_jika_password_salah(client):
    app.dependency_overrides[get_health_checks] = lambda: {"database": lambda: None}
    client.headers.pop("Authorization")
    assert not run(client, "admin@toko.com", "salah")
