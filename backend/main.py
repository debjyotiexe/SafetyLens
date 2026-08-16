import base64, os, time
import sqlite3
import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

from config import (MODEL_PATH, CONFIDENCE, SNAPSHOT_DIR, CAMERA_ID, RELEVANT_CLASSES,DB_PATH)
from compliance import check_compliance
from database import init_db, log_violation, get_stats

app = FastAPI(title="SafetyLens AI")
init_db()
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

print("Loading model...")
model = YOLO(MODEL_PATH)
RELEVANT_IDS = [i for i, name in model.names.items() if name in RELEVANT_CLASSES]
print(f"Model ready. Watching only: {[model.names[i] for i in RELEVANT_IDS]}")

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

@app.websocket("/ws/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    print("[+] Camera client connected")
    try:
        while True:
            data = await ws.receive_bytes()
            frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            results = model.predict(frame, conf=CONFIDENCE, classes=RELEVANT_IDS, verbose=False)
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
    except WebSocketDisconnect:
        print("[-] Camera client disconnected")

@app.get("/api/stats")
def stats():
    return get_stats()

@app.get("/api/snapshots")
def snapshots():
    files = sorted(os.listdir(SNAPSHOT_DIR), reverse=True)[:12]
    return [{"name": f, "url": f"/snapshots/{f}"} for f in files if f.endswith(".jpg")]

@app.post("/api/reset")
def reset():
    # wipe all logged violations + alerts
    with sqlite3.connect(DB_PATH) as c:
        c.execute("DELETE FROM alerts")
        c.execute("DELETE FROM violations")
        c.execute("DELETE FROM sqlite_sequence")   # reset auto-increment to 0
    # wipe snapshot images
    for f in os.listdir(SNAPSHOT_DIR):
        if f.endswith(".jpg"):
            try: os.remove(os.path.join(SNAPSHOT_DIR, f))
            except OSError: pass
    return {"status": "reset"}

app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_DIR), name="snapshots")

# VERY IMPORTANT: mount static files LAST!
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")