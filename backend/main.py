import base64, os, time, sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO

from config import SNAPSHOT_DIR, DB_PATH, CAMERA_ID, RELEVANT_CLASSES, SETTINGS, MODEL_OPTIONS, ALERT_SETTINGS
from database import (
    init_db, log_violation, get_stats, verify_login, check_token,
    get_incidents, resolve_incident, export_incidents_csv, update_camera_status,
    register_user, DuplicateUserError, revoke_token, list_users, set_user_role, toggle_user_active
)
from pipeline import process_frame
from alert_dispatch import dispatcher
from camera_manager import CameraManager

app = FastAPI(title="SafetyLens AI")
init_db()
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

camera_manager = None

@app.on_event("startup")
def startup_event():
    global camera_manager
    camera_manager = CameraManager(model, RELEVANT_IDS)
    for cam in camera_manager.cameras.values():
        if cam.get("status") in ("online", "starting", "error"):
            camera_manager.start_camera(cam["id"])

@app.on_event("shutdown")
def shutdown_event():
    if camera_manager:
        camera_manager.stop_all()

# ---------- model management ----------
model = None
RELEVANT_IDS = []
LOADED_MODEL = [None]

def load_model(key):
    global model, RELEVANT_IDS
    meta = MODEL_OPTIONS.get(key, {})
    path = meta.get("path")
    if not path or not os.path.exists(path):
        print(f"[!] Model file missing for '{key}': {path}")
        return False
    print(f"Loading model [{key}] ...")
    model = YOLO(path)
    RELEVANT_IDS = [i for i, name in model.names.items() if name in RELEVANT_CLASSES]
    LOADED_MODEL[0] = key
    print(f"Model ready. Watching only: {[model.names[i] for i in RELEVANT_IDS]}")
    return True

if not load_model(SETTINGS["model"]):
    loaded_alt = False
    for _k in MODEL_OPTIONS:
        if load_model(_k):
            SETTINGS["model"] = _k
            loaded_alt = True
            break
    if not loaded_alt:
        print("[!] No models available. Entering DEGRADED mode.")
        LOADED_MODEL[0] = "DEGRADED"
        model = None

# ---------- auth ----------
def get_user(authorization: str = Header(default=None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = check_token(token)
    if not user:
        raise HTTPException(401, "Unauthorized")
    return user

def get_admin(user=Depends(get_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user

class LoginBody(BaseModel):
    username: str
    password: str

class RegisterBody(BaseModel):
    username: str
    password: str
    email: str | None = None

class RoleBody(BaseModel):
    role: str

class SettingsBody(BaseModel):
    settings: dict

# ---------- auth routes ----------
@app.post("/api/register", status_code=201)
def api_register(body: RegisterBody):
    try:
        res = register_user(body.username, body.password, body.email)
        return {"status": "registered", "username": res["username"], "role": res["role"]}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except DuplicateUserError as e:
        raise HTTPException(409, str(e))

@app.post("/api/login")
def login(body: LoginBody):
    res = verify_login(body.username, body.password)
    if res and "error" in res:
        if res["error"] == "locked":
            retry_after = res.get("retry_after", 60)
            raise HTTPException(
                status_code=429,
                detail=f"Account temporarily locked due to failed login attempts. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )
        elif res["error"] == "disabled":
            raise HTTPException(403, "Account is disabled")
    if not res:
        raise HTTPException(401, "Invalid credentials")
    return res

@app.post("/api/logout")
def api_logout(authorization: str = Header(default=None), user=Depends(get_user)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if token:
        revoke_token(token)
    return {"status": "logged_out"}

@app.get("/api/me")
def me(user=Depends(get_user)):
    return user

# ---------- user management routes (admin) ----------
@app.get("/api/users")
def api_list_users(user=Depends(get_admin)):
    return list_users()

@app.post("/api/users/{user_id}/role")
def api_set_user_role(user_id: int, body: RoleBody, user=Depends(get_admin)):
    try:
        res = set_user_role(user_id, body.role)
        if not res:
            raise HTTPException(404, "User not found")
        return {"status": "updated", **res}
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/users/{user_id}/toggle-active")
def api_toggle_user_active(user_id: int, user=Depends(get_admin)):
    try:
        res = toggle_user_active(user_id, user["username"])
        if not res:
            raise HTTPException(404, "User not found")
        return {"status": "updated", **res}
    except ValueError as e:
        raise HTTPException(400, str(e))

# ---------- settings routes ----------
@app.get("/api/settings")
def read_settings(user=Depends(get_user)):
    models_status = []
    for k, meta in MODEL_OPTIONS.items():
        path = meta.get("path")
        models_status.append({
            "id": k,
            "name": meta.get("name", k),
            "available": os.path.exists(path) if path else False
        })
    return {"settings": SETTINGS, "models": models_status, "active": LOADED_MODEL[0]}

@app.post("/api/settings")
def write_settings(body: SettingsBody, user=Depends(get_admin)):
    for k, v in body.settings.items():
        if k in SETTINGS and k != "model":
            SETTINGS[k] = v
    msg = "applied"
    if body.settings.get("model") and body.settings["model"] != LOADED_MODEL[0]:
        if load_model(body.settings["model"]):
            SETTINGS["model"] = body.settings["model"]
            if camera_manager:
                camera_manager.model = model
                camera_manager.relevant_ids = RELEVANT_IDS
            msg = "applied + model reloaded"
    return {"status": msg, "settings": SETTINGS}

class AlertSettingsBody(BaseModel):
    settings: dict

@app.get("/api/settings/alerts")
def get_alert_settings(user=Depends(get_user)):
    return ALERT_SETTINGS

@app.post("/api/settings/alerts")
def set_alert_settings(body: AlertSettingsBody, user=Depends(get_admin)):
    ALERT_SETTINGS.update(body.settings)
    dispatcher.update_settings(ALERT_SETTINGS)
    return {"status": "applied", "settings": ALERT_SETTINGS}

@app.post("/api/settings/alerts/test")
def test_alert_settings(user=Depends(get_admin)):
    dummy_v = {"type": "TEST_ALERT", "conf": 1.0, "timestamp": time.time(), "box": [0,0,0,0]}
    res = {}
    res["log"] = dispatcher.log_handler.send(dummy_v, "", "test_cam")
    if ALERT_SETTINGS.get("email", {}).get("enabled"):
        res["email"] = dispatcher.email_handler.send(dummy_v, "", "test_cam")
    if ALERT_SETTINGS.get("webhook", {}).get("enabled"):
        res["webhook"] = dispatcher.webhook_handler.send(dummy_v, "", "test_cam")
    return {"status": "tested", "results": res}

class CameraBody(BaseModel):
    name: str
    type: str
    uri: str

YOUTUBE_REJECT_MSG = ("YouTube links are not supported (OpenCV cannot decode YouTube streams). "
                      "Use a local server file path or an rtsp:// stream.")

def validate_camera_source(cam_type: str, uri: str):
    if cam_type == "file":
        if not os.path.isfile(uri):
            raise HTTPException(400, f"File not found on server: {uri}")
        return
    if cam_type == "rtsp":
        low = uri.lower()
        if "youtube.com" in low or "youtu.be" in low:
            raise HTTPException(400, YOUTUBE_REJECT_MSG)
        if not uri.startswith("rtsp://"):
            raise HTTPException(400, "Invalid RTSP uri: must start with rtsp://")
        return
    raise HTTPException(400, f"Unsupported camera type: {cam_type}")

@app.get("/api/cameras")
def api_get_cameras(user=Depends(get_user)):
    return camera_manager.list_cameras()

@app.post("/api/cameras")
def api_add_camera(body: CameraBody, user=Depends(get_admin)):
    validate_camera_source(body.type, body.uri)
    cam_id = camera_manager.add_camera(body.name, body.type, body.uri)
    return {"status": "added", "id": cam_id}

@app.post("/api/cameras/{cam_id}/start")
def api_start_camera(cam_id: str, user=Depends(get_admin)):
    cam = next((c for c in camera_manager.list_cameras() if c["id"] == cam_id), None)
    if not cam:
        raise HTTPException(404, "Camera not found")
    try:
        validate_camera_source(cam["type"], cam["uri"])
    except HTTPException as e:
        update_camera_status(cam_id, "error", e.detail)
        raise
    camera_manager.start_camera(cam_id)
    return {"status": "started"}

@app.post("/api/cameras/{cam_id}/stop")
def api_stop_camera(cam_id: str, user=Depends(get_admin)):
    camera_manager.stop_camera(cam_id)
    return {"status": "stopped"}

@app.delete("/api/cameras/{cam_id}")
def api_delete_camera(cam_id: str, user=Depends(get_admin)):
    camera_manager.stop_camera(cam_id)
    from database import delete_camera
    delete_camera(cam_id)
    if cam_id in camera_manager.cameras:
        del camera_manager.cameras[cam_id]
    return {"status": "deleted"}

@app.get("/api/cameras/{cam_id}/snapshot")
def api_camera_snapshot(cam_id: str, user=Depends(get_user)):
    snap = camera_manager.get_snapshot(cam_id)
    if not snap:
        raise HTTPException(404, "No snapshot available")
    return Response(content=snap, media_type="image/jpeg")

# ---------- live stream ----------
@app.websocket("/ws/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    print("[+] Camera client connected")
    while True:
        try:
            data = await ws.receive_bytes()
        except WebSocketDisconnect:
            print("[-] Camera client disconnected")
            break

        try:
            result = process_frame(data, CAMERA_ID, model, RELEVANT_IDS, SETTINGS)
            if result is None:
                continue

            payload = {
                "frame": base64.b64encode(result["jpeg_bytes"]).decode(),
                "detections": result["detections"],
                "violations": result["violations"],
                "ts": result["ts"],
            }
            if "error" in result:
                payload["error"] = result["error"]
            await ws.send_json(payload)
        except Exception as e:
            print(f"[!] Frame processing error: {e}")
            continue

# ---------- data routes ----------
@app.get("/api/stats")
def stats(user=Depends(get_user)):
    return get_stats()

@app.get("/api/incidents")
def api_get_incidents(
    user=Depends(get_user),
    type: str = None,
    camera: str = None,
    from_date: str = None,
    to_date: str = None,
    status: str = None,
    page: int = 1,
    limit: int = 50
):
    return get_incidents(type=type, camera=camera, from_date=from_date, to_date=to_date, status=status, page=page, limit=limit)

@app.post("/api/incidents/{vid}/resolve")
def api_resolve_incident(vid: int, user=Depends(get_admin)):
    updated = resolve_incident(vid, user["username"])
    if not updated:
        raise HTTPException(404, "Incident not found")
    return updated

@app.get("/api/incidents/export")
def api_export_incidents(
    user=Depends(get_user),
    type: str = None,
    camera: str = None,
    from_date: str = None,
    to_date: str = None,
    status: str = None
):
    csv_data = export_incidents_csv({
        "type": type,
        "camera": camera,
        "from_date": from_date,
        "to_date": to_date,
        "status": status
    })
    return Response(content=csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=incidents.csv"})

@app.get("/api/snapshots")
def snapshots(user=Depends(get_user)):
    files = sorted(os.listdir(SNAPSHOT_DIR), reverse=True)[:12]
    return [{"name": f, "url": f"/snapshots/{f}"} for f in files if f.endswith(".jpg")]

@app.post("/api/reset")
def reset(user=Depends(get_admin)):
    with sqlite3.connect(DB_PATH) as c:
        c.execute("DELETE FROM alerts")
        c.execute("DELETE FROM violations")
        try: c.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError: pass
    for f in os.listdir(SNAPSHOT_DIR):
        if f.endswith(".jpg"):
            try: os.remove(os.path.join(SNAPSHOT_DIR, f))
            except OSError: pass
    return {"status": "reset"}

app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

LANDING_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "landing.html")

@app.get("/")
async def read_landing():
    target = LANDING_PATH if os.path.exists(LANDING_PATH) else "../frontend/landing.html"
    return FileResponse(target)

# VERY IMPORTANT: mount static files LAST!
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
