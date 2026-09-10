import pytest
from fastapi.testclient import TestClient

import config
import database
from main import app, get_user, get_admin
from camera_manager import CameraManager

config.DB_PATH = "test_camera_validation.db"
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_env(tmp_path):
    database.init_db()
    with database._conn() as c:
        c.execute("DELETE FROM cameras")

    import main
    mgr = CameraManager(None, [])
    old_mgr = main.camera_manager
    main.camera_manager = mgr

    def override_get_user():
        return {"username": "admin", "role": "admin"}
    def override_get_admin():
        return {"username": "admin", "role": "admin"}
    app.dependency_overrides[get_user] = override_get_user
    app.dependency_overrides[get_admin] = override_get_admin
    yield tmp_path
    app.dependency_overrides.clear()
    main.camera_manager = old_mgr
    with database._conn() as c:
        c.execute("DELETE FROM cameras")

def test_add_rejects_missing_file(tmp_path):
    uri = str(tmp_path / "missing.mp4")
    res = client.post("/api/cameras", json={"name": "F", "type": "file", "uri": uri})
    assert res.status_code == 400
    assert res.json()["detail"] == f"File not found on server: {uri}"
    assert database.list_cameras() == []

def test_add_accepts_existing_file(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake")
    res = client.post("/api/cameras", json={"name": "F", "type": "file", "uri": str(f)})
    assert res.status_code == 200
    assert res.json()["status"] == "added"
    assert len(database.list_cameras()) == 1

def test_add_rejects_youtube_watch_url():
    res = client.post("/api/cameras", json={
        "name": "Y", "type": "rtsp", "uri": "https://www.youtube.com/watch?v=abc"})
    assert res.status_code == 400
    assert "YouTube links are not supported" in res.json()["detail"]
    assert database.list_cameras() == []

def test_add_rejects_youtu_be_short_url():
    res = client.post("/api/cameras", json={
        "name": "Y", "type": "rtsp", "uri": "https://youtu.be/dQw4w9WgXcQ"})
    assert res.status_code == 400
    assert "YouTube links are not supported" in res.json()["detail"]

def test_add_rejects_non_rtsp_uri():
    res = client.post("/api/cameras", json={
        "name": "H", "type": "rtsp", "uri": "http://cam.local/stream"})
    assert res.status_code == 400
    assert "rtsp://" in res.json()["detail"]

def test_add_accepts_valid_rtsp():
    res = client.post("/api/cameras", json={
        "name": "R", "type": "rtsp", "uri": "rtsp://host:554/live"})
    assert res.status_code == 200

def test_add_rejects_unknown_type():
    res = client.post("/api/cameras", json={
        "name": "U", "type": "hls", "uri": "http://x/y.m3u8"})
    assert res.status_code == 400
    assert "Unsupported camera type" in res.json()["detail"]

def test_start_persists_error_msg_for_invalid_source():
    database.upsert_camera("cam_bad", "YT", "rtsp", "https://youtube.com/watch?v=1")
    res = client.post("/api/cameras/cam_bad/start")
    assert res.status_code == 400
    assert "YouTube links are not supported" in res.json()["detail"]
    cams = {c["id"]: c for c in database.list_cameras()}
    assert cams["cam_bad"]["status"] == "error"
    assert "YouTube links are not supported" in cams["cam_bad"]["error_msg"]

def test_start_persists_error_msg_for_deleted_file(tmp_path):
    f = tmp_path / "gone.mp4"
    f.write_bytes(b"x")
    database.upsert_camera("cam_f", "F", "file", str(f))
    f.unlink()
    res = client.post("/api/cameras/cam_f/start")
    assert res.status_code == 400
    assert res.json()["detail"] == f"File not found on server: {f}"
    cams = {c["id"]: c for c in database.list_cameras()}
    assert cams["cam_f"]["status"] == "error"
    assert cams["cam_f"]["error_msg"].startswith("File not found on server")

def test_start_404_unknown_camera():
    res = client.post("/api/cameras/cam_ghost/start")
    assert res.status_code == 404
