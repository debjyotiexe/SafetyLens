import cv2
import threading
import uuid
import config
import pipeline
from compliance import make_compliance_state
from database import list_cameras, upsert_camera, update_camera_status, delete_camera

class CameraManager:
    def __init__(self, model, relevant_ids):
        self.model = model
        self.relevant_ids = relevant_ids
        
        # In-memory states
        self.cameras = {}        # Dict[str, dict]
        self.threads = {}        # Dict[str, threading.Thread]
        self.stop_events = {}    # Dict[str, threading.Event]
        self.snapshots = {}      # Dict[str, bytes]
        self.states = {}         # Dict[str, dict]
        
        # Load existing cameras from DB
        for cam in list_cameras():
            self.cameras[cam["id"]] = cam

    def add_camera(self, name, type, uri) -> str:
        cam_id = f"cam_{uuid.uuid4().hex[:8]}"
        upsert_camera(cam_id, name, type, uri)
        
        # Update local cache
        for cam in list_cameras():
            if cam["id"] == cam_id:
                self.cameras[cam_id] = cam
                break
        return cam_id

    def start_camera(self, cam_id):
        if cam_id in self.threads and self.threads[cam_id].is_alive():
            return
            
        if cam_id not in self.cameras:
            # Refresh cache just in case
            for cam in list_cameras():
                if cam["id"] == cam_id:
                    self.cameras[cam_id] = cam
            if cam_id not in self.cameras:
                return
                
        self.stop_events[cam_id] = threading.Event()
        self.states[cam_id] = make_compliance_state()
        
        thread = threading.Thread(
            target=self._capture_loop,
            args=(cam_id, self.cameras[cam_id]["uri"]),
            daemon=True
        )
        self.threads[cam_id] = thread
        thread.start()

    def stop_camera(self, cam_id):
        if cam_id in self.stop_events:
            self.stop_events[cam_id].set()
            if cam_id in self.threads:
                self.threads[cam_id].join(timeout=2.0)
                del self.threads[cam_id]
            del self.stop_events[cam_id]
        update_camera_status(cam_id, 'offline')
        
    def stop_all(self):
        for cam_id in list(self.threads.keys()):
            self.stop_camera(cam_id)

    def get_snapshot(self, cam_id) -> bytes:
        return self.snapshots.get(cam_id)
        
    def list_cameras(self):
        # Sync with database
        db_cams = list_cameras()
        result = []
        for cam in db_cams:
            cam_id = cam["id"]
            self.cameras[cam_id] = cam
            cam_copy = dict(cam)
            if cam_id in self.threads and self.threads[cam_id].is_alive():
                cam_copy["live"] = True
            result.append(cam_copy)
        return result

    def _capture_loop(self, cam_id, uri):
        update_camera_status(cam_id, 'starting')
        stop_event = self.stop_events[cam_id]
        
        try:
            backoff = 1.0
            while not stop_event.is_set():
                cap = cv2.VideoCapture(uri)
                if not cap.isOpened():
                    update_camera_status(cam_id, 'error', f"Cannot open {uri}")
                    if stop_event.wait(backoff): break
                    backoff = min(backoff * 2, 30.0)
                    continue
                
                update_camera_status(cam_id, 'online')
                backoff = 1.0
                
                while not stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret:
                        break # Stream ended or dropped, reconnect
                        
                    # Encode raw frame to JPEG bytes for pipeline
                    success, buf = cv2.imencode('.jpg', frame)
                    if not success: 
                        continue
                        
                    # Run shared pipeline with ISOLATED compliance state
                    result = pipeline.process_frame(
                        buf.tobytes(), cam_id, self.model, self.relevant_ids, 
                        config.SETTINGS, compliance_state=self.states[cam_id]
                    )
                    
                    if result and 'jpeg_bytes' in result:
                        self.snapshots[cam_id] = result['jpeg_bytes']
                        
                    # Throttle frame rate
                    if stop_event.wait(getattr(config, 'CAMERA_FRAME_INTERVAL', 0.1)):
                        break
                        
                cap.release()
                if not stop_event.is_set():
                    update_camera_status(cam_id, 'offline')
                
        except Exception as e:
            update_camera_status(cam_id, 'error', str(e))
            print(f"[-] Camera {cam_id} capture loop crashed: {e}")
        finally:
            if 'cap' in locals() and cap.isOpened():
                cap.release()
            if not stop_event.is_set():
                update_camera_status(cam_id, 'offline')
