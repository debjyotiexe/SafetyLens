"""Unit and integration tests for Geofencing Zones (Sprint C-3 Steps 1 & 2).

Verifies database schema, migrations, CRUD operations, point-in-polygon math,
PPE zone breach tagging, RESTRICTED zone temporal confirmation/cooldown,
state cleanup, and frame drawing.
"""

import os
import time
import pytest
import numpy as np

import config
from config import SETTINGS
import database
from database import (
    init_db,
    create_zone,
    get_zones,
    get_zone_by_id,
    toggle_zone,
    delete_zone_by_id,
    upsert_camera,
    delete_camera,
)
import zones
from zones import (
    point_in_polygon,
    get_person_anchor,
    check_zones,
    draw_zones,
    clear_camera_zone_state,
    clear_zone_state,
    reset_all_zone_state,
)


import cv2
from fastapi import HTTPException
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Use isolated SQLite database, snapshot directory, and reset zone state for every test."""
    from main import app
    config.DB_PATH = str(tmp_path / "test_zones.db")
    config.SNAPSHOT_DIR = str(tmp_path / "snapshots")
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    init_db()
    reset_all_zone_state()
    SETTINGS.update({
        "confidence": 0.3,
        "min_frames": 3,
        "cooldown_sec": 10,
    })
    yield
    app.dependency_overrides.clear()
    reset_all_zone_state()


# ═════════════════════════════════════════════════════════════════════
# 1. Database Schema & Migration Tests
# ═════════════════════════════════════════════════════════════════════

def test_init_db_creates_zones_table_idempotently():
    """init_db should create zones table and remain safe across multiple invocations."""
    cols = database.table_columns("zones")
    expected = {"id", "camera_id", "name", "points", "requirement", "enabled", "created_at"}
    assert expected <= cols

    # Run init_db again to guarantee idempotency
    init_db()
    cols_again = database.table_columns("zones")
    assert expected <= cols_again


def test_zone_crud_lifecycle():
    """Full CRUD lifecycle for zones in the database."""
    poly = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
    z = create_zone("cam_test", "Zone A", poly, "HELMET")
    assert z["id"] is not None
    assert z["camera_id"] == "cam_test"
    assert z["name"] == "Zone A"
    assert z["requirement"] == "HELMET"
    assert z["points"] == poly
    assert z["enabled"] == 1

    # Fetch by camera
    all_cam = get_zones("cam_test")
    assert len(all_cam) == 1
    assert all_cam[0]["id"] == z["id"]
    assert all_cam[0]["points"] == poly

    # Fetch by ID
    single = get_zone_by_id(z["id"])
    assert single is not None
    assert single["name"] == "Zone A"

    # Toggle enabled
    toggled = toggle_zone(z["id"])
    assert toggled["enabled"] == 0

    # Enabled only filter
    assert len(get_zones("cam_test", enabled_only=True)) == 0

    # Toggle back
    toggle_zone(z["id"])
    assert len(get_zones("cam_test", enabled_only=True)) == 1

    # Delete
    assert delete_zone_by_id(z["id"]) is True
    assert get_zone_by_id(z["id"]) is None
    assert len(get_zones("cam_test")) == 0


def test_camera_deletion_cascades_zones():
    """Deleting a camera should clean up associated zones."""
    upsert_camera("cam_temp", "Temp Cam", "rtsp", "rtsp://localhost/stream")
    create_zone("cam_temp", "Z1", [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]], "VEST")
    assert len(get_zones("cam_temp")) == 1

    delete_camera("cam_temp")
    assert len(get_zones("cam_temp")) == 0


# ═════════════════════════════════════════════════════════════════════
# 2. Geometry & Coordinate Math Tests
# ═════════════════════════════════════════════════════════════════════

def test_point_in_polygon_convex():
    square = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    assert point_in_polygon((0.5, 0.5), square) is True
    assert point_in_polygon((1.5, 0.5), square) is False
    assert point_in_polygon((-0.1, 0.5), square) is False
    assert point_in_polygon((0.5, -0.1), square) is False


def test_point_in_polygon_concave_l_shape():
    # L-shape polygon in [0, 2] x [0, 2]
    # (0,0) -> (2,0) -> (2,1) -> (1,1) -> (1,2) -> (0,2)
    l_poly = [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [1.0, 1.0], [1.0, 2.0], [0.0, 2.0]]
    assert point_in_polygon((0.5, 0.5), l_poly) is True   # lower-left
    assert point_in_polygon((1.5, 0.5), l_poly) is True   # lower-right
    assert point_in_polygon((0.5, 1.5), l_poly) is True   # upper-left
    assert point_in_polygon((1.5, 1.5), l_poly) is False  # cutout area!


def test_point_in_polygon_invalid_inputs():
    assert point_in_polygon((0.5, 0.5), []) is False
    assert point_in_polygon((0.5, 0.5), [[0.1, 0.1], [0.2, 0.2]]) is False


def test_get_person_anchor_bottom_center():
    # Frame shape (480, 640) -> height=480, width=640
    box = [100, 100, 200, 400]  # x1=100, y1=100, x2=200, y2=400
    nx, ny = get_person_anchor(box, frame_shape=(480, 640))
    # cx = (100 + 200) / 2 = 150 -> nx = 150 / 640 = 0.234375
    # cy = 400 -> ny = 400 / 480 = 0.833333
    assert pytest.approx(nx, 0.001) == 150.0 / 640.0
    assert pytest.approx(ny, 0.001) == 400.0 / 480.0


def test_get_person_anchor_normalized_passthrough():
    # Box already in normalized coordinates 0..1
    box = [0.2, 0.2, 0.4, 0.8]
    nx, ny = get_person_anchor(box)
    assert pytest.approx(nx, 0.001) == 0.3
    assert pytest.approx(ny, 0.001) == 0.8


# ═════════════════════════════════════════════════════════════════════
# 3. PPE Zone Breach Tagging Tests
# ═════════════════════════════════════════════════════════════════════

def test_ppe_zone_breach_tagging_matching_requirement():
    """Confirmed violation inside matching zone is tagged with zone_name and severity CRITICAL."""
    # Zone covers [0.1, 0.1] to [0.5, 0.5]
    create_zone("cam_01", "Hardhat Area", [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]], "HELMET")

    # Person with bottom-center anchor at cx=0.3, cy=0.4 (inside zone)
    v = {"type": "NO_HELMET", "box": [0.2, 0.2, 0.4, 0.4], "conf": 0.9, "pid": 1}
    breaches = check_zones("cam_01", [], [v])

    assert len(breaches) == 1
    assert v["zone_name"] == "Hardhat Area"
    assert v["severity"] == "CRITICAL"


def test_ppe_zone_breach_ignored_when_outside_zone():
    """Confirmed violation outside zone is NOT tagged."""
    create_zone("cam_01", "Hardhat Area", [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]], "HELMET")

    # Person anchor at cx=0.8, cy=0.8 (outside zone)
    v = {"type": "NO_HELMET", "box": [0.7, 0.7, 0.9, 0.8], "conf": 0.9, "pid": 1}
    breaches = check_zones("cam_01", [], [v])

    assert len(breaches) == 0
    assert "zone_name" not in v


def test_ppe_zone_breach_ignored_when_requirement_mismatch():
    """NO_VEST violation in HELMET zone should not be tagged."""
    create_zone("cam_01", "Hardhat Area", [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]], "HELMET")

    v = {"type": "NO_VEST", "box": [0.2, 0.2, 0.4, 0.4], "conf": 0.9, "pid": 1}
    breaches = check_zones("cam_01", [], [v])

    assert len(breaches) == 0
    assert "zone_name" not in v


def test_any_ppe_zone_matches_any_violation():
    """ANY_PPE zone matches NO_HELMET, NO_VEST, NO_GLOVES, NO_BOOTS, NO_GOGGLES."""
    create_zone("cam_01", "High Risk Zone", [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], "ANY_PPE")

    v_gloves = {"type": "NO_GLOVES", "box": [0.2, 0.2, 0.4, 0.4], "conf": 0.85, "pid": 1}
    breaches = check_zones("cam_01", [], [v_gloves])

    assert len(breaches) == 1
    assert v_gloves["zone_name"] == "High Risk Zone"
    assert v_gloves["severity"] == "CRITICAL"


# ═════════════════════════════════════════════════════════════════════
# 4. RESTRICTED Zone Streak & Cooldown Tests
# ═════════════════════════════════════════════════════════════════════

def test_restricted_zone_streak_progression_and_cooldown():
    """RESTRICTED zone requires min_frames streak before emitting ZONE_BREACH, then obeys cooldown."""
    SETTINGS["min_frames"] = 3
    SETTINGS["cooldown_sec"] = 5

    create_zone("cam_01", "Danger Zone", [[0.1, 0.1], [0.6, 0.1], [0.6, 0.6], [0.1, 0.6]], "RESTRICTED")

    # Person inside zone
    person = {"cls": "Person", "conf": 0.95, "box": [0.2, 0.2, 0.4, 0.5], "pid": 42}

    # Frame 1: streak = 1 -> no breach
    b1 = check_zones("cam_01", [person], [])
    assert len(b1) == 0

    # Frame 2: streak = 2 -> no breach
    b2 = check_zones("cam_01", [person], [])
    assert len(b2) == 0

    # Frame 3: streak = 3 -> BREACH!
    b3 = check_zones("cam_01", [person], [])
    assert len(b3) == 1
    assert b3[0]["type"] == "ZONE_BREACH"
    assert b3[0]["zone_name"] == "Danger Zone"
    assert b3[0]["severity"] == "CRITICAL"
    assert b3[0]["pid"] == 42

    # Frame 4: immediately next frame -> cooldown suppresses
    b4 = check_zones("cam_01", [person], [])
    assert len(b4) == 0


def test_restricted_zone_streak_decays_when_person_leaves():
    """Streak decays when track leaves zone."""
    SETTINGS["min_frames"] = 3
    create_zone("cam_01", "Danger Zone", [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]], "RESTRICTED")

    p_inside = {"cls": "Person", "conf": 0.9, "box": [0.2, 0.2, 0.4, 0.4], "pid": 10}
    p_outside = {"cls": "Person", "conf": 0.9, "box": [0.8, 0.8, 0.9, 0.9], "pid": 10}

    # Frame 1 & 2 inside
    check_zones("cam_01", [p_inside], [])
    check_zones("cam_01", [p_inside], [])
    from zones import _restricted_streaks
    assert _restricted_streaks.get(("cam_01", 1, 10)) == 2

    # Frame 3 moves outside -> streak decays to 1
    check_zones("cam_01", [p_outside], [])
    assert _restricted_streaks.get(("cam_01", 1, 10)) == 1

    # Frame 4 moves outside again -> streak drops to 0 and is purged
    check_zones("cam_01", [p_outside], [])
    assert ("cam_01", 1, 10) not in _restricted_streaks


def test_state_cleanup_on_camera_or_zone_removal():
    """State cleanup helper functions purge dictionaries properly."""
    from zones import _restricted_streaks, _restricted_cooldowns
    _restricted_streaks[("cam_01", 1, 5)] = 3
    _restricted_cooldowns[("cam_01", 1, 5)] = time.time()
    _restricted_streaks[("cam_02", 2, 7)] = 2

    clear_camera_zone_state("cam_01")
    assert ("cam_01", 1, 5) not in _restricted_streaks
    assert ("cam_01", 1, 5) not in _restricted_cooldowns
    assert ("cam_02", 2, 7) in _restricted_streaks

    clear_zone_state(2)
    assert ("cam_02", 2, 7) not in _restricted_streaks


# ═════════════════════════════════════════════════════════════════════
# 5. Visual Frame Drawing Tests
# ═════════════════════════════════════════════════════════════════════

def test_draw_zones_renders_without_exception():
    """draw_zones should render translucent polygon and label badge onto frame."""
    create_zone("cam_vis", "Restricted Area", [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]], "RESTRICTED")
    create_zone("cam_vis", "Helmet Zone", [[0.2, 0.2], [0.4, 0.2], [0.4, 0.4], [0.2, 0.4]], "HELMET")

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    annotated = draw_zones(frame, "cam_vis")

    assert annotated is not None
    assert annotated.shape == (480, 640, 3)
    # The frame should no longer be completely black
    assert np.any(annotated > 0)


# ═════════════════════════════════════════════════════════════════════
# 6. API Endpoints & Pipeline Integration Tests
# ═════════════════════════════════════════════════════════════════════

def test_api_create_zone_admin_only():
    from main import app, get_user, get_admin
    client = TestClient(app)

    # 1. As viewer: GET allowed, POST rejected with 403
    app.dependency_overrides[get_user] = lambda: {"username": "view1", "role": "viewer"}
    def override_get_admin_viewer():
        raise HTTPException(403, "Admin access required")
    app.dependency_overrides[get_admin] = override_get_admin_viewer

    get_res = client.get("/api/zones")
    assert get_res.status_code == 200

    payload = {
        "camera_id": "cam_01",
        "name": "Admin Only Zone",
        "points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
        "requirement": "HELMET",
    }
    post_res = client.post("/api/zones", json=payload)
    assert post_res.status_code == 403

    # 2. As admin: POST allowed with 201
    app.dependency_overrides[get_admin] = lambda: {"username": "admin", "role": "admin"}
    admin_post = client.post("/api/zones", json=payload)
    assert admin_post.status_code == 201
    data = admin_post.json()
    assert data["status"] == "created"
    assert data["zone"]["name"] == "Admin Only Zone"
    assert data["zone"]["requirement"] == "HELMET"


def test_api_create_zone_invalid_polygon():
    from main import app, get_admin, get_user
    client = TestClient(app)

    app.dependency_overrides[get_user] = lambda: {"username": "admin", "role": "admin"}
    app.dependency_overrides[get_admin] = lambda: {"username": "admin", "role": "admin"}

    # Case A: < 3 points
    res = client.post("/api/zones", json={
        "camera_id": "cam_01",
        "name": "Bad Poly",
        "points": [[0.1, 0.1], [0.5, 0.5]],
        "requirement": "VEST"
    })
    assert res.status_code == 400

    # Case B: Out-of-bounds coords (> 1.0)
    res = client.post("/api/zones", json={
        "camera_id": "cam_01",
        "name": "Bad Poly 2",
        "points": [[0.1, 0.1], [1.5, 0.5], [0.1, 0.5]],
        "requirement": "VEST"
    })
    assert res.status_code == 400

    # Case C: Negative coordinates (< 0.0)
    res = client.post("/api/zones", json={
        "camera_id": "cam_01",
        "name": "Bad Poly 3",
        "points": [[-0.2, 0.1], [0.5, 0.5], [0.1, 0.5]],
        "requirement": "VEST"
    })
    assert res.status_code == 400

    # Case D: Invalid requirement
    res = client.post("/api/zones", json={
        "camera_id": "cam_01",
        "name": "Bad Poly 4",
        "points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
        "requirement": "NOT_A_VALID_REQ"
    })
    assert res.status_code == 400


def test_api_toggle_and_delete():
    from main import app, get_admin, get_user
    client = TestClient(app)

    app.dependency_overrides[get_user] = lambda: {"username": "admin", "role": "admin"}
    app.dependency_overrides[get_admin] = lambda: {"username": "admin", "role": "admin"}

    # Create zone
    create_res = client.post("/api/zones", json={
        "camera_id": "cam_01",
        "name": "Toggle Zone",
        "points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
        "requirement": "BOOTS"
    })
    assert create_res.status_code == 201
    zone_id = create_res.json()["zone"]["id"]
    assert create_res.json()["zone"]["enabled"] == 1

    # Toggle off
    t_res1 = client.post(f"/api/zones/{zone_id}/toggle")
    assert t_res1.status_code == 200
    assert t_res1.json()["zone"]["enabled"] == 0
    assert get_zone_by_id(zone_id)["enabled"] == 0

    # Toggle on
    t_res2 = client.post(f"/api/zones/{zone_id}/toggle")
    assert t_res2.status_code == 200
    assert t_res2.json()["zone"]["enabled"] == 1
    assert get_zone_by_id(zone_id)["enabled"] == 1

    # Delete
    del_res = client.delete(f"/api/zones/{zone_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"
    assert get_zone_by_id(zone_id) is None

    # Delete non-existent -> 404
    del_404 = client.delete(f"/api/zones/{zone_id}")
    assert del_404.status_code == 404

    # Toggle non-existent -> 404
    t_404 = client.post(f"/api/zones/{zone_id}/toggle")
    assert t_404.status_code == 404


def make_jpeg(width=640, height=480):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


class MockBox:
    def __init__(self, cls, conf, xyxy):
        self.cls = [cls]
        self.conf = [conf]
        self.xyxy = [xyxy]


class MockResult:
    def __init__(self, boxes):
        self.boxes = boxes


class MockYOLOPerson:
    """Returns a single person detection inside the restricted zone."""
    def __init__(self):
        self.names = {0: "Person"}

    def predict(self, frame, **kwargs):
        # Anchor on 640x480: cx = 150/640=0.234, cy = 250/480=0.521 (inside zone [0.1..0.8])
        return [MockResult([MockBox(0, 0.95, [100, 100, 200, 250])])]


def test_pipeline_logs_restricted_breach():
    from pipeline import process_frame
    from database import get_incidents

    create_zone("cam_01", "Restricted Area", [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]], "RESTRICTED")
    model = MockYOLOPerson()
    jpeg = make_jpeg()

    # Frame 1: streak = 1 -> no breach
    res1 = process_frame(jpeg, "cam_01", model, [0], SETTINGS)
    assert not any(v["type"] == "ZONE_BREACH" for v in res1["violations"])

    # Frame 2: streak = 2 -> no breach
    res2 = process_frame(jpeg, "cam_01", model, [0], SETTINGS)
    assert not any(v["type"] == "ZONE_BREACH" for v in res2["violations"])

    # Frame 3: streak = 3 -> ZONE_BREACH triggered!
    res3 = process_frame(jpeg, "cam_01", model, [0], SETTINGS)
    breaches = [v for v in res3["violations"] if v["type"] == "ZONE_BREACH"]
    assert len(breaches) == 1
    assert breaches[0]["zone_name"] == "Restricted Area"
    assert breaches[0]["severity"] == "CRITICAL"

    # Assert incident is logged in database
    incidents = get_incidents(type="ZONE_BREACH")["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["camera_id"] == "cam_01"
    assert incidents[0]["type"] == "ZONE_BREACH"

    # Assert snapshot is saved on disk
    snap_files = [f for f in os.listdir(config.SNAPSHOT_DIR) if "ZONE_BREACH" in f]
    assert len(snap_files) >= 1


def test_zones_static_serving():
    from main import app
    client = TestClient(app)

    res_html = client.get("/zones.html")
    assert res_html.status_code == 200
    assert "GEOFENCING // ZONES" in res_html.text
    assert "zone-canvas" in res_html.text
    assert "zones.js?v=7" in res_html.text
    assert "shell.js?v=7" in res_html.text

    res_js = client.get("/js/zones.js")
    assert res_js.status_code == 200
    assert "zone-canvas" in res_js.text
    assert "NO SIGNAL - DRAWING ON CALIBRATION GRID" in res_js.text


