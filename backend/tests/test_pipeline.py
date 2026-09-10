"""Regression tests for pipeline.process_frame and compliance state isolation.

Every test uses tmp_path for DB + snapshot isolation.  Mock YOLO models
ensure no GPU, webcam, or network access is required.
"""

import pytest
import os
import base64

import cv2
import numpy as np

import config
from config import SETTINGS
from compliance import _trackers, _streak, _cooldown


# ═════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def isolate(tmp_path):
    """Reset all mutable state before each test."""
    config.DB_PATH = str(tmp_path / "test_pipeline.db")
    config.SNAPSHOT_DIR = str(tmp_path / "snapshots")
    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)

    from database import init_db
    init_db()

    _trackers.clear()
    _streak.clear()
    _cooldown.clear()

    SETTINGS.update({
        "confidence": 0.3,
        "negative_confidence": 0.15,
        "min_frames": 1,
        "cooldown_sec": 0,
        "check_vest": True,
    })
    yield


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════

def make_jpeg(width=640, height=480):
    """Create a minimal valid JPEG byte string."""
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


class MockYOLO:
    """Returns one Person + one no_helmet (in head zone)."""
    def __init__(self):
        self.names = {0: "Person", 1: "no_helmet"}

    def predict(self, frame, **kwargs):
        return [MockResult([
            MockBox(0, 0.9, [100, 100, 200, 400]),   # Person
            MockBox(1, 0.9, [120, 110, 180, 170]),    # no_helmet in head zone
        ])]


class MockYOLOEmpty:
    """Returns zero detections."""
    def __init__(self):
        self.names = {0: "Person"}

    def predict(self, frame, **kwargs):
        return [MockResult([])]


# ═════════════════════════════════════════════════════════════════════
# process_frame — structure & content
# ═════════════════════════════════════════════════════════════════════

def test_process_frame_returns_correct_structure():
    from pipeline import process_frame

    result = process_frame(make_jpeg(), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    assert result is not None
    assert isinstance(result["jpeg_bytes"], bytes)
    assert isinstance(result["detections"], list)
    assert isinstance(result["violations"], list)
    assert isinstance(result["ts"], float)


def test_process_frame_detections_match_model():
    from pipeline import process_frame

    result = process_frame(make_jpeg(), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    assert len(result["detections"]) == 2
    cls_names = {d["cls"] for d in result["detections"]}
    assert cls_names == {"Person", "no_helmet"}

    for d in result["detections"]:
        assert set(d.keys()) == {"cls", "conf", "box"}
        assert len(d["box"]) == 4
        assert all(isinstance(x, int) for x in d["box"])


def test_process_frame_violations_detected():
    from pipeline import process_frame

    result = process_frame(make_jpeg(), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    types = {v["type"] for v in result["violations"]}
    assert "NO_HELMET" in types
    assert "NO_VEST" in types


# ═════════════════════════════════════════════════════════════════════
# process_frame — edge cases
# ═════════════════════════════════════════════════════════════════════

def test_process_frame_degraded_mode():
    from pipeline import process_frame

    result = process_frame(make_jpeg(), "cam_test", None, [], SETTINGS)

    assert result is not None
    assert result["detections"] == []
    assert result["violations"] == []
    assert result["error"] == "DEGRADED_MODE"
    assert isinstance(result["jpeg_bytes"], bytes)


def test_process_frame_invalid_jpeg_returns_none():
    from pipeline import process_frame

    result = process_frame(b"not a jpeg", "cam_test", MockYOLO(), [0, 1], SETTINGS)
    assert result is None


def test_process_frame_no_violations_when_compliant():
    from pipeline import process_frame

    SETTINGS["check_vest"] = False
    result = process_frame(make_jpeg(), "cam_test", MockYOLOEmpty(), [0], SETTINGS)

    assert result["violations"] == []


# ═════════════════════════════════════════════════════════════════════
# process_frame — side effects
# ═════════════════════════════════════════════════════════════════════

def test_process_frame_logs_violations_to_db():
    from pipeline import process_frame
    from database import get_stats

    process_frame(make_jpeg(), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    stats = get_stats()
    assert stats["total"] >= 2  # NO_HELMET + NO_VEST at minimum
    types_in_db = [t[0] for t in stats["by_type"]]
    assert "NO_HELMET" in types_in_db
    assert "NO_VEST" in types_in_db


def test_process_frame_saves_snapshots():
    from pipeline import process_frame

    process_frame(make_jpeg(), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    snaps = [f for f in os.listdir(config.SNAPSHOT_DIR) if f.endswith(".jpg")]
    assert len(snaps) >= 2  # one per violation


def test_process_frame_annotated_jpeg_is_valid():
    from pipeline import process_frame

    result = process_frame(make_jpeg(1200, 800), "cam_test", MockYOLO(), [0, 1], SETTINGS)

    # Verify the JPEG bytes are decodable
    decoded = cv2.imdecode(
        np.frombuffer(result["jpeg_bytes"], np.uint8), cv2.IMREAD_COLOR
    )
    assert decoded is not None
    # Width should be resized to 800 (original was 1200)
    assert decoded.shape[1] == 800


# ═════════════════════════════════════════════════════════════════════
# Compliance state isolation (Step 2)
# ═════════════════════════════════════════════════════════════════════

def test_compliance_state_isolation():
    from compliance import check_compliance, make_compliance_state

    state_a = make_compliance_state()
    state_b = make_compliance_state()

    dets = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]},
        {"cls": "no_helmet", "conf": 0.9, "box": [120, 110, 180, 170]},
    ]

    SETTINGS["check_vest"] = False
    SETTINGS["min_frames"] = 1
    SETTINGS["cooldown_sec"] = 0

    # Run on state_a — violation should fire
    viols_a = check_compliance(dets, state=state_a)
    assert len(viols_a) == 1
    assert viols_a[0]["type"] == "NO_HELMET"

    # state_b is independent — its own streak starts fresh
    viols_b = check_compliance(dets, state=state_b)
    assert len(viols_b) == 1
    assert viols_b[0]["type"] == "NO_HELMET"

    # Module globals must be untouched
    assert len(_streak) == 0
    assert len(_cooldown) == 0
    assert len(_trackers) == 0


def test_compliance_state_cooldown_independent():
    from compliance import check_compliance, make_compliance_state

    SETTINGS["check_vest"] = False
    SETTINGS["min_frames"] = 1
    SETTINGS["cooldown_sec"] = 10

    dets = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]},
        {"cls": "no_helmet", "conf": 0.9, "box": [120, 110, 180, 170]},
    ]

    state_a = make_compliance_state()
    state_b = make_compliance_state()

    # First call on state_a — fires
    assert len(check_compliance(dets, state=state_a)) == 1
    # Second call on state_a — cooldown blocks it
    assert len(check_compliance(dets, state=state_a)) == 0

    # state_b has no cooldown history — should still fire
    assert len(check_compliance(dets, state=state_b)) == 1


def test_make_compliance_state_returns_correct_keys():
    from compliance import make_compliance_state

    state = make_compliance_state()
    assert set(state.keys()) == {"cooldown", "streak", "trackers"}
    assert state["cooldown"] == {}
    assert state["streak"] == {}
    assert state["trackers"] == {}


# ═════════════════════════════════════════════════════════════════════
# WebSocket parity — the contract must NOT change
# ═════════════════════════════════════════════════════════════════════

def test_websocket_json_shape_parity():
    """The WS handler must produce the exact same JSON shape as Phase 1."""
    from fastapi.testclient import TestClient
    import main
    import database

    database.init_db()

    main.model = MockYOLO()
    main.RELEVANT_IDS = [0, 1]

    client = TestClient(main.app)

    with client.websocket_connect("/ws/stream") as websocket:
        websocket.send_bytes(make_jpeg())
        data = websocket.receive_json()

    # Phase 1 contract: exactly these keys
    assert "frame" in data
    assert "detections" in data
    assert "violations" in data
    assert "ts" in data

    # frame must be a valid base64 string
    assert isinstance(data["frame"], str)
    base64.b64decode(data["frame"])  # must not raise

    # detections shape
    for d in data["detections"]:
        assert set(d.keys()) == {"cls", "conf", "box"}

    # violations shape
    for v in data["violations"]:
        assert "type" in v
        assert "box" in v
        assert "conf" in v

    # ts is a float
    assert isinstance(data["ts"], float)

    # no unexpected extra keys in normal mode
    assert "error" not in data


def test_websocket_degraded_mode_parity():
    """Degraded mode must produce the correct JSON shape."""
    from fastapi.testclient import TestClient
    import main
    import database

    database.init_db()

    main.model = None

    client = TestClient(main.app)

    with client.websocket_connect("/ws/stream") as websocket:
        websocket.send_bytes(make_jpeg())
        data = websocket.receive_json()

    assert data["detections"] == []
    assert data["violations"] == []
    assert data["error"] == "DEGRADED_MODE"
    assert isinstance(data["frame"], str)
