import os
import config
from database import init_db, log_violation, get_stats, verify_login

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