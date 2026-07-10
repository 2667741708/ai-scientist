from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

try:
    from backend import auth_store
    from backend.app import app
except ModuleNotFoundError:
    import auth_store
    from app import app


def _configure_isolated_auth_store(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_store, "AUTH_DB_PATH", tmp_path / "accounts.sqlite3")
    monkeypatch.setattr(auth_store, "LOCAL_ACCOUNT_SECRETS_PATH", tmp_path / "local-account-secrets.json")
    monkeypatch.setattr(auth_store, "DEFAULT_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(auth_store, "DEFAULT_ADMIN_PASSWORD", "AdminPass123!")
    auth_store.init_auth_store()


def test_auth_login_register_and_admin_user_management(monkeypatch, tmp_path):
    _configure_isolated_auth_store(monkeypatch, tmp_path)

    with TestClient(app) as client:
        missing = client.get("/api/auth/me")
        assert missing.status_code == 401

        admin_login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "AdminPass123!"},
        )
        assert admin_login.status_code == 200
        admin_payload = admin_login.json()
        assert admin_payload["ok"] is True
        assert admin_payload["code"] == "auth.login.success"
        assert admin_payload["http_status"] == 200
        admin_token = admin_payload["access_token"]
        assert admin_payload["user"]["role"] == "admin"
        assert "users:manage" in admin_payload["user"]["permissions"]

        bad_login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "WrongPass123!"},
        )
        assert bad_login.status_code == 401
        assert bad_login.json()["detail"]["code"] == "auth.login.invalid_credentials"
        assert bad_login.json()["detail"]["http_status"] == 401

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert me.status_code == 200
        assert me.json()["user"]["email"] == "admin@example.com"

        researcher_register = client.post(
            "/api/auth/register",
            json={"email": "student@example.com", "password": "StudentPass123!", "display_name": "Student"},
        )
        assert researcher_register.status_code == 200
        researcher_payload = researcher_register.json()
        assert researcher_payload["ok"] is True
        assert researcher_payload["code"] == "auth.register.success"
        assert researcher_payload["http_status"] == 200
        researcher_token = researcher_payload["access_token"]
        assert researcher_payload["user"]["role"] == "researcher"

        duplicate_register = client.post(
            "/api/auth/register",
            json={"email": "student@example.com", "password": "StudentPass123!", "display_name": "Student"},
        )
        assert duplicate_register.status_code == 409
        assert duplicate_register.json()["detail"]["code"] == "auth.register.account_exists"
        assert duplicate_register.json()["detail"]["http_status"] == 409

        denied = client.get("/api/admin/users", headers={"Authorization": f"Bearer {researcher_token}"})
        assert denied.status_code == 403

        created = client.post(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": "operator@example.com",
                "password": "OperatorPass123!",
                "display_name": "Operator",
                "role": "researcher",
            },
        )
        assert created.status_code == 200
        created_payload = created.json()
        user_id = created_payload["user"]["id"]
        assert created_payload["local_secret_path"] == str(tmp_path / "local-account-secrets.json")

        secrets = json.loads((tmp_path / "local-account-secrets.json").read_text(encoding="utf-8"))
        operator_secret = next(item for item in secrets["accounts"] if item["email"] == "operator@example.com")
        assert operator_secret["password"] == "OperatorPass123!"
        assert operator_secret["source"] == "admin_create_user"

        with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
            password_hash = db.execute("SELECT password_hash FROM accounts WHERE email = ?", ("operator@example.com",)).fetchone()[0]
        assert password_hash.startswith("pbkdf2_sha256$")
        assert password_hash != "OperatorPass123!"

        reset = client.put(
            f"/api/admin/users/{user_id}/password",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"password": "ResetPass123!"},
        )
        assert reset.status_code == 200
        assert reset.json()["local_secret_path"] == str(tmp_path / "local-account-secrets.json")
        secrets = json.loads((tmp_path / "local-account-secrets.json").read_text(encoding="utf-8"))
        operator_secret = next(item for item in secrets["accounts"] if item["email"] == "operator@example.com")
        assert operator_secret["password"] == "ResetPass123!"
        assert operator_secret["source"] == "admin_reset_password"

        disabled = client.put(
            f"/api/admin/users/{user_id}/status",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "disabled"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["user"]["status"] == "disabled"


def test_local_admin_username_accepts_six_character_password(monkeypatch, tmp_path):
    _configure_isolated_auth_store(monkeypatch, tmp_path)
    local_admin = auth_store.create_account(
        "admin",
        "123456",
        display_name="Local Admin",
        role="admin",
    )
    auth_store.record_local_account_secret(
        local_admin,
        "123456",
        source="local_admin_create",
        actor_email="admin@example.com",
    )

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "admin", "password": "123456"})
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "admin"

    with sqlite3.connect(tmp_path / "accounts.sqlite3") as db:
        password_hash = db.execute("SELECT password_hash FROM accounts WHERE email = 'admin'").fetchone()[0]
    assert password_hash.startswith("pbkdf2_sha256$")
    assert password_hash != "123456"

    secrets = json.loads((tmp_path / "local-account-secrets.json").read_text(encoding="utf-8"))
    saved_admin = next(item for item in secrets["accounts"] if item["email"] == "admin")
    assert saved_admin["password"] == "123456"

    with pytest.raises(ValueError, match="8"):
        auth_store.create_account("weak-admin@example.com", "123456", role="admin")
