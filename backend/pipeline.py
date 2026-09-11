"""Shared inference pipeline for SafetyLens AI.

Extracts the frame-processing logic from the WebSocket handler into a
reusable function that can be called from both the browser path and
background camera threads.
"""

import os
import time

import cv2
import numpy as np

import config
from compliance import check_compliance
from database import log_violation
from alert_dispatch import dispatcher
try:
    from zones import check_zones, draw_zones
except ImportError:
    from backend.zones import check_zones, draw_zones

# ---------- visual helpers (moved from main.py) ----------
COLORS = {
    "Person": (0, 170, 255), "person": (0, 170, 255),
    "helmet": (0, 255, 0), "Hardhat": (0, 255, 0), "vest": (0, 255, 0),
    "no_helmet": (0, 0, 255), "NO-Hardhat": (0, 0, 255),
}


def draw_boxes(frame, detections, violations):
    """Draw detection and violation bounding boxes on a frame."""
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
    """Crop and save a snapshot around the violation bounding box."""
    x1, y1, x2, y2 = v["box"]
    crop = frame[max(0, y1 - 40):y2 + 60, max(0, x1 - 40):x2 + 40]
    path = os.path.join(config.SNAPSHOT_DIR, f"{int(time.time()*1000)}_{v['type']}.jpg")
    cv2.imwrite(path, crop)
    return path


def process_frame(frame_bytes, camera_id, model, relevant_ids, settings,
                  compliance_state=None):
    """Run the full inference + compliance pipeline on a single JPEG frame.

    Args:
        frame_bytes:      Raw JPEG bytes.
        camera_id:        Camera identifier for violation logging.
        model:            Loaded YOLO model instance, or None for degraded mode.
        relevant_ids:     List of class IDs to detect.
        settings:         Runtime settings dict (confidence, negative_confidence …).
        compliance_state: Optional per-camera compliance state from
                          ``make_compliance_state()``.  If *None*, uses the shared
                          module-level state (backward-compatible browser path).

    Returns:
        dict with keys ``jpeg_bytes``, ``detections``, ``violations``, ``ts``,
        and optionally ``error``.  Returns ``None`` if the frame cannot be decoded.
    """
    frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return None

    # Degraded mode — no model loaded
    if model is None:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return {
            "jpeg_bytes": buf.tobytes(),
            "detections": [],
            "violations": [],
            "ts": time.time(),
            "error": "DEGRADED_MODE",
        }

    # --- inference ---
    inference_conf = min(settings["confidence"],
                        settings.get("negative_confidence", 0.15))
    results = model.predict(frame, conf=inference_conf,
                            classes=relevant_ids, verbose=False)
    detections = [
        {"cls": model.names[int(b.cls[0])],
         "conf": float(b.conf[0]),
         "box": list(map(int, b.xyxy[0]))}
        for b in results[0].boxes
    ]

    # --- compliance ---
    violations = check_compliance(detections, state=compliance_state)
    zone_breaches = check_zones(camera_id, detections, violations, frame.shape[:2], compliance_state)

    for v in violations:
        snap = save_snapshot(frame, v)
        vid = log_violation(v["type"], v["conf"], snap, camera_id)
        print(f"!!! VIOLATION #{vid}: {v['type']} ({v['conf']:.2f})")
        dispatcher.dispatch(v, snap, camera_id)

    for b in zone_breaches:
        if b.get("type") == "ZONE_BREACH":
            snap = save_snapshot(frame, b)
            vid = log_violation(b["type"], b["conf"], snap, camera_id)
            print(f"!!! ZONE BREACH #{vid}: {b['type']} ({b.get('zone_name', '')})")
            dispatcher.dispatch(b, snap, camera_id)
            violations.append(b)

    # --- annotate ---
    annotated = draw_boxes(frame.copy(), detections, violations)
    annotated = draw_zones(annotated, camera_id)
    h, w = annotated.shape[:2]
    if w > 800:
        scale = 800 / w
        annotated = cv2.resize(annotated, (800, int(h * scale)))

    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return {
        "jpeg_bytes": buf.tobytes(),
        "detections": detections,
        "violations": violations,
        "ts": time.time(),
    }
