import os
import time
import pytest
from fastapi.testclient import TestClient

import config
import database
from database import (
    init_db, _conn, hash_pw, hash_pw_pbkdf2, reset_throttling
)
from main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_auth_env(tmp_path):
    config.DB_PATH = str(tmp_path / "test_auth.db")
    config.LOGIN_THROTTLE_ENABLED = False
    config.LOGIN_THROTTLE_LIMIT = 3
    config.LOGIN_THROTTLE_LOCKOUT_SEC = 2
    config.TOKEN_TTL_HOURS = 12
    reset_throttling()

    init_db()
    yield
    reset_throttling()


def test_register_success():
    res = client.post("/api/register", json={
        "username": "new_operator",
        "password": "validpassword123",
        "email": "operator@safety.local"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "registered"
    assert data["username"] == "new_operator"
    assert data["role"] == "viewer"

    with _conn() as c:
        row = c.execute("SELECT username, password_hash, role, is_active, email FROM users WHERE username=?",
                        ("new_operator",)).fetchone()
        assert row is not None
        assert row[0] == "new_operator"
        assert row[1].startswith("pbkdf2$")
        assert row[2] == "viewer"
        assert row[3] == 1
        assert row[4] == "operator@safety.local"


def test_register_duplicate_409():
    client.post("/api/register", json={
        "username": "dup_operator",
        "password": "validpassword123"
    })
    res = client.post("/api/register", json={
        "username": "dup_operator",
        "password": "anotherpassword123"
    })
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


def test_register_validation_errors():
    # Password too short (< 8 chars)
    res = client.post("/api/register", json={
        "username": "short_pw_user",
        "password": "123"
    })
    assert res.status_code == 400
    assert "at least 8 characters" in res.json()["detail"]

    # Empty username
    res = client.post("/api/register", json={
        "username": "   ",
        "password": "validpassword123"
    })
    assert res.status_code == 400


def test_legacy_sha256_login_and_lazy_upgrade():
    # Insert user with legacy SHA-256 hash (simulating existing DB before migration)
    legacy_salt = "abcd1234efgh5678"
    legacy_hash = hash_pw("legacysecret123", legacy_salt)
    with _conn() as c:
        c.execute(
            "INSERT INTO users (username, password_hash, salt, role, is_active) VALUES (?,?,?,?,1)",
            ("legacy_user", legacy_hash, legacy_salt, "viewer")
        )

    # Verify initial DB state is legacy
    with _conn() as c:
        h = c.execute("SELECT password_hash FROM users WHERE username='legacy_user'").fetchone()[0]
        assert not h.startswith("pbkdf2$")

    # Login with legacy credentials
    res = client.post("/api/login", json={
        "username": "legacy_user",
        "password": "legacysecret123"
    })
    assert res.status_code == 200
    token = res.json()["token"]
    assert token

    # Check that the hash was lazily upgraded to PBKDF2 in SQLite
    with _conn() as c:
        new_hash = c.execute("SELECT password_hash FROM users WHERE username='legacy_user'").fetchone()[0]
        assert new_hash.startswith("pbkdf2$")

    # Second login with upgraded hash must succeed
    res2 = client.post("/api/login", json={
        "username": "legacy_user",
        "password": "legacysecret123"
    })
    assert res2.status_code == 200


def test_token_ttl_expiry():
    # Login to generate token
    res = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    token = res.json()["token"]

    # Authenticated call succeeds
    me_res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200

    # Fast forward token created_at by 13 hours in SQLite
    with _conn() as c:
        c.execute("UPDATE tokens SET created_at = datetime('now', '-13 hours') WHERE token = ?", (token,))

    # Token must now be rejected as expired and purged
    me_res_expired = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res_expired.status_code == 401

    # Verify token row was purged
    with _conn() as c:
        row = c.execute("SELECT 1 FROM tokens WHERE token = ?", (token,)).fetchone()
        assert row is None


def test_logout_revocation():
    # Login
    res = client.post("/api/login", json={"username": "viewer", "password": "view123"})
    token = res.json()["token"]

    # Call logout
    logout_res = client.post("/api/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "logged_out"

    # Subsequent call with revoked token must return 401
    me_res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 401


def test_login_throttling_lockout():
    config.LOGIN_THROTTLE_ENABLED = True
    config.LOGIN_THROTTLE_LIMIT = 3
    config.LOGIN_THROTTLE_LOCKOUT_SEC = 2
    reset_throttling()

    # 3 failed attempts
    for _ in range(3):
        r = client.post("/api/login", json={"username": "admin", "password": "wrongpassword"})
        assert r.status_code == 401

    # 4th attempt (even with correct password) returns 429 Too Many Requests
    r_locked = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert r_locked.status_code == 429
    assert "temporarily locked" in r_locked.json()["detail"]
    assert "Retry-After" in r_locked.headers


def test_login_throttling_disabled_in_tests():
    config.LOGIN_THROTTLE_ENABLED = False
    reset_throttling()

    # 6 failed attempts when disabled -> no 429 lockout
    for _ in range(6):
        r = client.post("/api/login", json={"username": "admin", "password": "wrongpassword"})
        assert r.status_code == 401

    # Immediate correct password succeeds
    r_ok = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert r_ok.status_code == 200


def test_disabled_user_cannot_login():
    with _conn() as c:
        c.execute("UPDATE users SET is_active = 0 WHERE username = 'viewer'")

    res = client.post("/api/login", json={"username": "viewer", "password": "view123"})
    assert res.status_code == 403
    assert "disabled" in res.json()["detail"]


def test_disabling_user_revokes_active_sessions():
    # Login viewer
    res = client.post("/api/login", json={"username": "viewer", "password": "view123"})
    viewer_token = res.json()["token"]

    # Login admin
    res_admin = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    admin_token = res_admin.json()["token"]

    # Viewer can access /api/me
    assert client.get("/api/me", headers={"Authorization": f"Bearer {viewer_token}"}).status_code == 200

    # Find viewer id
    with _conn() as c:
        viewer_id = c.execute("SELECT id FROM users WHERE username = 'viewer'").fetchone()[0]

    # Admin disables viewer
    toggle_res = client.post(
        f"/api/users/{viewer_id}/toggle-active",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] == 0

    # Viewer's session is immediately revoked
    assert client.get("/api/me", headers={"Authorization": f"Bearer {viewer_token}"}).status_code == 401


def test_admin_cannot_demote_last_admin():
    res_admin = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    admin_token = res_admin.json()["token"]

    with _conn() as c:
        admin_id = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]

    # Demoting the only admin must fail with 400
    res = client.post(
        f"/api/users/{admin_id}/role",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    assert "Cannot demote the last active administrator" in res.json()["detail"]


def test_admin_cannot_disable_self_or_last_admin():
    res_admin = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    admin_token = res_admin.json()["token"]

    with _conn() as c:
        admin_id = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]

    # Disabling self must fail
    res = client.post(
        f"/api/users/{admin_id}/toggle-active",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    assert "Cannot disable your own account" in res.json()["detail"]


def test_viewer_forbidden_from_user_management():
    res_viewer = client.post("/api/login", json={"username": "viewer", "password": "view123"})
    viewer_token = res_viewer.json()["token"]
    headers = {"Authorization": f"Bearer {viewer_token}"}

    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users/1/role", json={"role": "viewer"}, headers=headers).status_code == 403
    assert client.post("/api/users/1/toggle-active", headers=headers).status_code == 403


def test_landing_page_serves_landing_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "INDUSTRIAL COMPUTER VISION" in res.text
    assert "AUTHENTICATE OPERATOR" in res.text
    assert "sl_token" in res.text  # client guard present


def test_login_and_register_static_serving():
    res_login = client.get("/login.html")
    assert res_login.status_code == 200
    assert "NEW OPERATOR? REGISTER ACCOUNT" in res_login.text

    res_reg = client.get("/register.html")
    assert res_reg.status_code == 200
    assert "REGISTER OPERATOR" in res_reg.text
    assert "CONFIRM PASSCODE" in res_reg.text


def test_users_static_serving():
    res_users = client.get("/users.html")
    assert res_users.status_code == 200
    assert "OPERATOR MANAGEMENT" in res_users.text
    assert "users.js?v=5" in res_users.text

    res_js = client.get("/js/users.js")
    assert res_js.status_code == 200
    assert "handleRoleChange" in res_js.text
    assert "handleToggleActive" in res_js.text
