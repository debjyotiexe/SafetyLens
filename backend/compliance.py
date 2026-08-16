import time
from config import VIOLATION_CLASSES, SETTINGS

_cooldown = {}
_streak = {}

def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0

def check_compliance(detections):
    S = SETTINGS
    now = time.time()
    candidates = []

    # Direct missing-gear classes
    for d in detections:
        if d["conf"] >= S["person_conf"]:
            vtype = VIOLATION_CLASSES.get(d["cls"])
            if vtype:
                candidates.append({"type": vtype, "box": d["box"], "conf": d["conf"]})

    # Geometric: person present, gear missing?
    persons = [d for d in detections if d["cls"] in ("Person", "person") and d["conf"] >= S["person_conf"]]
    helmets = [d for d in detections if d["cls"] in ("helmet", "Hardhat") and d["conf"] >= S["gear_conf"]]
    vests   = [d for d in detections if d["cls"] == "vest" and d["conf"] >= S["gear_conf"]]

    for p in persons:
        x1, y1, x2, y2 = p["box"]
        h = y2 - y1
        head_zone  = [x1, y1, x2, y1 + 0.25 * h]
        torso_zone = [x1, y1 + 0.20 * h, x2, y1 + 0.75 * h]

        if not any(iou(hm["box"], head_zone) > 0.1 for hm in helmets):
            candidates.append({"type": "NO_HELMET", "box": p["box"], "conf": p["conf"]})
        if S["check_vest"] and not any(iou(v["box"], torso_zone) > 0.1 for v in vests):
            candidates.append({"type": "NO_VEST", "box": p["box"], "conf": p["conf"]})

    # Temporal voting + cooldown
    kept = []
    for v in candidates:
        key = (v["type"], v["box"][0] // 160, v["box"][1] // 160)
        _streak[key] = _streak.get(key, 0) + 1
        if _streak[key] < S["min_frames"]:
            continue
        if now - _cooldown.get(key, 0) < S["cooldown_sec"]:
            continue
        _cooldown[key] = now
        _streak[key] = 0
        kept.append(v)
    return kept