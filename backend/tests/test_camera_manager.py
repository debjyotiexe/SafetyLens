import pytest
from unittest.mock import patch, MagicMock
from camera_manager import CameraManager
import database
import config
import os
import time
import numpy as np

config.DB_PATH = "test_camera_manager.db"

@pytest.fixture(autouse=True)
def setup():
    if os.path.exists(config.DB_PATH):
        try: os.remove(config.DB_PATH)
        except OSError: pass
    database.init_db()
    with database._conn() as c:
        c.execute("DELETE FROM cameras")
    yield
    with database._conn() as c:
        c.execute("DELETE FROM cameras")

@pytest.fixture
def manager():
    mgr = CameraManager("dummy_model", [1, 2, 3])
    config.CAMERA_FRAME_INTERVAL = 0.01 
    yield mgr
    mgr.stop_all()

@patch("cv2.VideoCapture")
@patch("cv2.imencode")
@patch("pipeline.process_frame")
def test_lifecycle_and_snapshot(mock_process, mock_imencode, mock_videocapture, manager):
    # Mock video capture
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    # ret, frame (use a dummy numpy array to avoid imencode crashing if we don't mock it well, actually we mocked imencode)
    mock_cap.read.side_effect = [(True, np.zeros((10,10,3), dtype=np.uint8))] * 10 + [(False, None)]
    mock_videocapture.return_value = mock_cap
    
    # Mock imencode to just return success and dummy buffer
    mock_imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
    
    # Mock pipeline
    mock_process.return_value = {"jpeg_bytes": b"fake_annotated_jpeg", "detections": [], "violations": [], "ts": 123}
    
    # Add camera
    cam_id = manager.add_camera("test_cam", "rtsp", "rtsp://test")
    assert cam_id in manager.cameras
    
    # Start camera
    manager.start_camera(cam_id)
    assert cam_id in manager.threads
    assert manager.threads[cam_id].is_alive()
    
    # Wait for snapshot
    for _ in range(20):
        if manager.get_snapshot(cam_id):
            break
        time.sleep(0.05)
    
    # Check snapshot
    snap = manager.get_snapshot(cam_id)
    assert snap == b"fake_annotated_jpeg"
    
    # Stop camera
    manager.stop_camera(cam_id)
    assert cam_id not in manager.threads
    
    # Check DB status is offline
    cams = database.list_cameras()
    assert cams[0]["status"] == "offline"

@patch("camera_manager.cv2.VideoCapture")
def test_error_handling(mock_videocapture, manager):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_videocapture.return_value = mock_cap
    
    cam_id = manager.add_camera("err_cam", "rtsp", "rtsp://err")
    manager.start_camera(cam_id)
    
    time.sleep(0.1)
    
    # DB status should be error
    cams = database.list_cameras()
    assert cams[0]["status"] == "error"
    assert "Cannot open" in cams[0]["error_msg"]
    
    manager.stop_camera(cam_id)

@patch("cv2.VideoCapture")
@patch("cv2.imencode")
@patch("pipeline.process_frame")
def test_isolation(mock_process, mock_imencode, mock_videocapture, manager):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((10,10,3), dtype=np.uint8))
    mock_videocapture.return_value = mock_cap
    mock_imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
    mock_process.return_value = {"jpeg_bytes": b"jpg", "detections": [], "violations": [], "ts": 123}
    
    cam1 = manager.add_camera("c1", "rtsp", "rtsp://1")
    cam2 = manager.add_camera("c2", "rtsp", "rtsp://2")
    
    manager.start_camera(cam1)
    manager.start_camera(cam2)
    
    time.sleep(0.1)
    
    state1 = manager.states[cam1]
    state2 = manager.states[cam2]
    
    assert state1 is not state2
    assert isinstance(state1, dict)
    assert "trackers" in state1
