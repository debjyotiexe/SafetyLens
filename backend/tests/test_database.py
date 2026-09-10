import os
import sqlite3
import config
from database import init_db, log_violation, get_stats, verify_login, list_users, table_columns

def test_full_db_flow():
    config.DB_PATH = "ci_test.db"
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)

    init_db()
    vid = log_violation("NO_HELMET", 0.9, "snap.jpg", "cam_01")
    assert vid == 1

    s = get_stats()
    assert s["total"] == 1
    assert s["by_type"] == [("NO_HELMET", 1)]

    auth = verify_login("admin", "admin123")
    assert auth and auth["role"] == "admin"
    assert verify_login("admin", "wrongpass") is None

    import gc
    gc.collect()
    try:
        os.remove(config.DB_PATH)
    except PermissionError:
        pass


def test_users_created_at_migration_from_old_db(tmp_path):
    test_db = str(tmp_path / "old_users.db")
    config.DB_PATH = test_db

    # Create old-style users table manually WITHOUT created_at, is_active, email
    with sqlite3.connect(test_db) as conn:
        conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
        );
        """)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?,?,?,?)",
            ("old_admin", "hash1", "salt1", "admin")
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?,?,?,?)",
            ("old_viewer", "hash2", "salt2", "viewer")
        )

    # Verify old schema has no created_at
    with sqlite3.connect(test_db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        assert "created_at" not in cols

    # Run init_db() to trigger migration
    init_db()

    # Assert PRAGMA table_info(users) includes created_at, is_active, email
    with sqlite3.connect(test_db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        assert "created_at" in cols
        assert "is_active" in cols
        assert "email" in cols

        # Assert existing rows now have non-null, non-empty created_at
        rows = conn.execute("SELECT username, created_at, is_active FROM users").fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r[1] is not None
            assert len(r[1]) > 0
            assert r[2] == 1  # is_active default

    # Assert list_users() does not crash and returns created_at
    users = list_users()
    assert len(users) == 2
    assert users[0]["username"] == "old_admin"
    assert users[0]["created_at"] != ""
    assert users[1]["username"] == "old_viewer"
    assert users[1]["created_at"] != ""


def test_init_db_idempotent_after_created_at_migration(tmp_path):
    test_db = str(tmp_path / "idempotent_migration.db")
    config.DB_PATH = test_db

    # Initialize once
    init_db()
    # Call again on migrated DB
    init_db()

    cols = table_columns("users")
    assert "created_at" in cols
    assert "is_active" in cols
    assert "email" in cols

    users = list_users()
    assert len(users) >= 2
    for u in users:
        assert u["created_at"] is not None
        assert u["created_at"] != ""