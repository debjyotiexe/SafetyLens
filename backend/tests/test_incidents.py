import pytest
from fastapi.testclient import TestClient
from main import app, get_user, get_admin
from database import init_db, log_violation, _conn
import os
import config
from datetime import datetime, timedelta

config.DB_PATH = "test_incidents.db"
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM violations")
        c.execute("DELETE FROM cameras")
        c.execute("DELETE FROM alerts")
    
    def override_get_user():
        return {"username": "admin", "role": "admin"}
    def override_get_admin():
        return {"username": "admin", "role": "admin"}
        
    app.dependency_overrides[get_user] = override_get_user
    app.dependency_overrides[get_admin] = override_get_admin
    yield
    app.dependency_overrides.clear()

def test_migration_idempotent():
    # setup_db already called init_db once
    init_db() # Should not raise any OperationalError

def test_pagination():
    # Insert 60 dummy violations
    for i in range(60):
        log_violation("NO_HELMET", 0.9, "snap.jpg", "cam_01")
        
    res = client.get("/api/incidents?limit=50")
    assert res.status_code == 200
    data = res.json()
    assert len(data["incidents"]) == 50
    assert data["total"] == 60
    assert data["pages"] == 2
    assert data["page"] == 1

def test_filters():
    log_violation("NO_HELMET", 0.9, "snap1.jpg", "cam_01")
    log_violation("NO_VEST", 0.8, "snap2.jpg", "cam_02")
    log_violation("NO_HELMET", 0.95, "snap3.jpg", "cam_02")
    
    res = client.get("/api/incidents?type=NO_HELMET")
    data = res.json()
    assert len(data["incidents"]) == 2
    
    res = client.get("/api/incidents?camera=cam_01")
    data = res.json()
    assert len(data["incidents"]) == 1
    assert data["incidents"][0]["type"] == "NO_HELMET"
    
    res = client.get("/api/incidents?camera=cam_02&type=NO_HELMET")
    data = res.json()
    assert len(data["incidents"]) == 1
    assert data["incidents"][0]["snapshot"] == "snap3.jpg"

def test_resolve_incident():
    vid = log_violation("NO_HELMET", 0.9, "snap1.jpg", "cam_01")
    
    res = client.post(f"/api/incidents/{vid}/resolve")
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "resolved"
    assert updated["resolved_by"] == "admin"
    assert updated["resolved_at"] is not None
    
    # Check DB
    with _conn() as c:
        row = c.execute("SELECT status, resolved_by FROM violations WHERE id=?", (vid,)).fetchone()
        assert row[0] == "resolved"
        assert row[1] == "admin"

def test_export_csv():
    log_violation("NO_HELMET", 0.9, "snap1.jpg", "cam_01")
    log_violation("NO_VEST", 0.8, "snap2.jpg", "cam_02")
    
    res = client.get("/api/incidents/export")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment; filename=incidents.csv" in res.headers["content-disposition"]
    
    content = res.text
    assert "id,camera_id,type,confidence,snapshot,created_at,status,resolved_at,resolved_by" in content
    assert "NO_HELMET" in content
    assert "NO_VEST" in content
    assert "cam_01" in content
    assert "cam_02" in content

def test_auth_viewer_cannot_resolve():
    def override_get_admin_viewer():
        from fastapi import HTTPException
        raise HTTPException(403, "Admin access required")
    app.dependency_overrides[get_admin] = override_get_admin_viewer
    
    vid = log_violation("NO_HELMET", 0.9, "snap1.jpg", "cam_01")
    res = client.post(f"/api/incidents/{vid}/resolve")
    assert res.status_code == 403

def test_read_path_contract_for_frontend_renderer():
    # incidents.js renders from {"incidents":[...], "total", "page", "pages"}
    # with row fields id/type/camera_id/confidence/snapshot/created_at/status
    log_violation("NO_HELMET", 0.91, "snapA.jpg", "cam_01")
    log_violation("NO_VEST", 0.84, "snapB.jpg", "cam_02")

    res = client.get("/api/incidents")
    assert res.status_code == 200
    data = res.json()
    assert set(data.keys()) == {"incidents", "total", "page", "pages"}
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["pages"] == 1
    assert len(data["incidents"]) == 2

    renderer_fields = {"id", "type", "camera_id", "confidence", "snapshot", "created_at", "status", "resolved_by"}
    for row in data["incidents"]:
        assert renderer_fields <= set(row.keys())
        assert isinstance(row["confidence"], float)
        assert isinstance(row["created_at"], str)

def test_export_csv_returns_bytes():
    log_violation("NO_HELMET", 0.91, "snapA.jpg", "cam_01")
    log_violation("NO_VEST", 0.84, "snapB.jpg", "cam_02")

    res = client.get("/api/incidents/export")
    assert res.status_code == 200
    raw = res.content
    assert isinstance(raw, bytes) and len(raw) > 0
    text = raw.decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "id,camera_id,type,confidence,snapshot,created_at,status,resolved_at,resolved_by"
    assert len(lines) == 3
    assert "NO_HELMET" in text and "cam_02" in text
