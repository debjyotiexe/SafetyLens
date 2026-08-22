import base64, os, time, sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO

from config import SNAPSHOT_DIR, DB_PATH, CAMERA_ID, RELEVANT_CLASSES, SETTINGS, MODEL_OPTIONS
from compliance import check_compliance
from database import init_db, log_violation, get_stats, verify_login, check_token

app = FastAPI(title="SafetyLens AI")
init_db()
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

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

class SettingsBody(BaseModel):
    settings: dict

# ---------- visual helpers ----------
COLORS = {
    "Person": (0, 170, 255), "person": (0, 170, 255),
    "helmet": (0, 255, 0), "Hardhat": (0, 255, 0), "vest": (0, 255, 0),
    "no_helmet": (0, 0, 255), "NO-Hardhat": (0, 0, 255),
}

def draw_boxes(frame, detections, violations):
    for d in detections:
        if d["conf"] < 0.5:
            continue
        x1, y1, x2, y2 = d["box"]
        color = COLORS.get(d["cls"], (255, 255, 255))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f"{d['cls']} {d['conf']:.2f}", (x1, max(12, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    for v in violations:
        x1, y1, x2, y2 = v["box"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(frame, v["type"], (x1, min(frame.shape[0] - 4, y2 + 18)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return frame

def save_snapshot(frame, v):
    x1, y1, x2, y2 = v["box"]
    crop = frame[max(0, y1 - 40):y2 + 60, max(0, x1 - 40):x2 + 40]
    path = os.path.join(SNAPSHOT_DIR, f"{int(time.time()*1000)}_{v['type']}.jpg")
    cv2.imwrite(path, crop)
    return path

# ---------- auth routes ----------
@app.post("/api/login")
def login(body: LoginBody):
    res = verify_login(body.username, body.password)
    if not res:
        raise HTTPException(401, "Invalid credentials")
    return res

@app.get("/api/me")
def me(user=Depends(get_user)):
    return user

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
            msg = "applied + model reloaded"
    return {"status": msg, "settings": SETTINGS}

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
            frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            if model is None:
                # Degraded mode: still send the frame, but no processing
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                await ws.send_json({
                    "frame": base64.b64encode(buf).decode(),
                    "detections": [],
                    "violations": [],
                    "ts": time.time(),
                    "error": "DEGRADED_MODE"
                })
                continue

            inference_conf = min(SETTINGS["confidence"], SETTINGS.get("negative_confidence", 0.15))
            results = model.predict(frame, conf=inference_conf, classes=RELEVANT_IDS, verbose=False)
            detections = [
                {"cls": model.names[int(b.cls[0])],
                 "conf": float(b.conf[0]),
                 "box": list(map(int, b.xyxy[0]))}
                for b in results[0].boxes
            ]

            violations = check_compliance(detections)
            for v in violations:
                snap = save_snapshot(frame, v)
                vid = log_violation(v["type"], v["conf"], snap, CAMERA_ID)
                print(f"!!! VIOLATION #{vid}: {v['type']} ({v['conf']:.2f})")

            annotated = draw_boxes(frame.copy(), detections, violations)
            h, w = annotated.shape[:2]
            if w > 800:
                scale = 800 / w
                annotated = cv2.resize(annotated, (800, int(h * scale)))

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
            await ws.send_json({
                "frame": base64.b64encode(buf).decode(),
                "detections": detections,
                "violations": violations,
                "ts": time.time(),
            })
        except Exception as e:
            print(f"[!] Frame processing error: {e}")
            continue

# ---------- data routes ----------
@app.get("/api/stats")
def stats(user=Depends(get_user)):
    return get_stats()

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

# VERY IMPORTANT: mount static files LAST!
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
