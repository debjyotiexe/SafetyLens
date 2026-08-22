import pytest
import os
import time
import base64
import cv2
import numpy as np

import config
from fastapi.testclient import TestClient
from main import app, load_model
import database
from database import get_stats

client = TestClient(app)

def setup_module():
    config.DB_PATH = "e2e_test.db"
    if os.path.exists(config.DB_PATH):
        try: os.remove(config.DB_PATH)
        except: pass
    database.init_db()

def teardown_module():
    import gc; gc.collect()
    try: os.remove(config.DB_PATH)
    except: pass

def test_api_roles_and_fallback():
    # Model fallback test
    assert client.get("/api/settings").status_code == 401 # needs auth
    
    # login as admin
    res = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    admin_token = res.json()["token"]
    
    # login as viewer
    res = client.post("/api/login", json={"username": "viewer", "password": "view123"})
    viewer_token = res.json()["token"]

    headers = {"Authorization": f"Bearer {viewer_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # settings get is allowed for viewer
    s = client.get("/api/settings", headers=headers).json()
    
    # viewer cannot POST settings
    assert client.post("/api/settings", json={"settings": {}}, headers=headers).status_code == 403
    
    # fallback to nonexistent model
    res = client.post("/api/settings", json={"settings": {"model": "nonexistent"}}, headers=admin_headers)
    assert res.status_code == 200
    
    # Check that it fell back to degraded or a valid model
    s2 = client.get("/api/settings", headers=headers).json()
    assert s2["active"] in ("v1-custom", "v0-hardhat", "DEGRADED")


def test_e2e_compliance_flow():
    # login
    admin_token = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # clear db
    client.post("/api/reset", headers=admin_headers)

    # set config for test
    client.post("/api/settings", json={"settings": {
        "min_frames": 1,
        "cooldown_sec": 0,
        "check_vest": True
    }}, headers=admin_headers)

    # We need to mock the YOLO model since we don't have weights in CI
    class MockYOLO:
        def __init__(self, *args, **kwargs):
            self.names = {0: "Person", 1: "no_helmet"}
        def predict(self, frame, **kwargs):
            class MockBox:
                def __init__(self, cls, conf, xyxy):
                    self.cls = [cls]
                    self.conf = [conf]
                    self.xyxy = [xyxy]
            class MockResult:
                def __init__(self):
                    self.boxes = [
                        MockBox(0, 0.9, [100, 100, 200, 400]), # Person
                        MockBox(1, 0.9, [120, 110, 180, 170])  # no_helmet
                    ]
            return [MockResult()]

    import main
    main.model = MockYOLO()
    main.RELEVANT_IDS = [0, 1]
    
    # Dummy frame
    img = np.zeros((600, 600, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    
    with client.websocket_connect("/ws/stream") as websocket:
        websocket.send_bytes(buf.tobytes())
        data = websocket.receive_json()
        
        # We expect NO_HELMET and NO_VEST (inferred)
        types = {v["type"] for v in data["violations"]}
        assert "NO_HELMET" in types
        assert "NO_VEST" in types
        
    # Check DB stats API
    stats = client.get("/api/stats", headers=admin_headers).json()
    assert stats["total"] >= 2
    types_in_db = [t[0] for t in stats["by_type"]]
    assert "NO_HELMET" in types_in_db
    assert "NO_VEST" in types_in_db
