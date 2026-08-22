import time
from config import SETTINGS

_cooldown = {}
_streak = {}
_trackers = {} # lightweight person tracking across frames

def center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

def in_zone(c, zone):
    return zone[0] <= c[0] <= zone[2] and zone[1] <= c[1] <= zone[3]

def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0

def get_person_ids(persons_boxes):
    now = time.time()

    # Age out missed ones
    to_delete = []
    for k, v in _trackers.items():
        if now - v['ts'] > 2.0 or v['missed'] > 10:
            to_delete.append(k)
    for k in to_delete:
        del _trackers[k]

    assigned = {}
    unassigned_boxes = list(range(len(persons_boxes)))
    unassigned_tracks = list(_trackers.keys())

    # Greedy IoU matching
    pairs = []
    for i, box in enumerate(persons_boxes):
        for k in unassigned_tracks:
            score = iou(box, _trackers[k]['box'])
            if score > 0.3: # IoU threshold
                pairs.append((score, i, k))

    pairs.sort(key=lambda x: x[0], reverse=True)

    assigned_tracks = set()
    assigned_boxes = set()
    for score, i, k in pairs:
        if i not in assigned_boxes and k not in assigned_tracks:
            assigned_boxes.add(i)
            assigned_tracks.add(k)
            assigned[i] = k
            _trackers[k]['box'] = persons_boxes[i]
            _trackers[k]['ts'] = now
            _trackers[k]['missed'] = 0

    # New tracks
    for i in unassigned_boxes:
        if i not in assigned_boxes:
            new_id = max(_trackers.keys(), default=0) + 1
            assigned[i] = new_id
            _trackers[new_id] = {'box': persons_boxes[i], 'ts': now, 'missed': 0}

    # Update missed
    for k in unassigned_tracks:
        if k not in assigned_tracks:
            _trackers[k]['missed'] += 1

    return assigned

def check_compliance(detections):
    S = SETTINGS
    now = time.time()
    candidates = []

    persons = [d for d in detections if d["cls"] in ("Person", "person") and d["conf"] >= S["confidence"]]

    pos_helmets = [d for d in detections if d["cls"] in ("helmet", "Hardhat") and d["conf"] >= S["confidence"]]
    pos_goggles = [d for d in detections if d["cls"] == "goggles" and d["conf"] >= S["confidence"]]
    pos_gloves = [d for d in detections if d["cls"] == "gloves" and d["conf"] >= S["confidence"]]
    pos_boots = [d for d in detections if d["cls"] == "boots" and d["conf"] >= S["confidence"]]
    vests = [d for d in detections if d["cls"] == "vest" and d["conf"] >= S["confidence"]]

    no_helmets = [d for d in detections if d["cls"] in ("no_helmet", "NO-Hardhat") and d["conf"] >= S.get("negative_confidence", 0.15)]
    no_goggles = [d for d in detections if d["cls"] == "no_goggle" and d["conf"] >= S.get("negative_confidence", 0.15)]
    no_gloves = [d for d in detections if d["cls"] == "no_gloves" and d["conf"] >= S.get("negative_confidence", 0.15)]
    no_boots = [d for d in detections if d["cls"] == "no_boots" and d["conf"] >= S.get("negative_confidence", 0.15)]

    box_to_pid = get_person_ids([p["box"] for p in persons])

    for i, p in enumerate(persons):
        pid = box_to_pid[i]
        x1, y1, x2, y2 = p["box"]
        w = x2 - x1
        h = y2 - y1

        head_zone = [x1, y1 - 0.1*h, x2, y1 + 0.3*h]
        torso_zone = [x1, y1 + 0.2*h, x2, y1 + 0.75*h]
        hands_zone = [x1 - 0.3*w, y1 + 0.4*h, x2 + 0.3*w, y2]
        feet_zone = [x1 - 0.2*w, y1 + 0.7*h, x2 + 0.2*w, y2 + 0.2*h]

        # Deterministic conflict handling: positive PPE suppresses negative PPE
        has_pos_helmet = any(iou(v["box"], head_zone) > 0.1 or in_zone(center(v["box"]), head_zone) for v in pos_helmets)
        has_neg_helmet = any(iou(n["box"], head_zone) > 0.1 or in_zone(center(n["box"]), head_zone) for n in no_helmets)
        if has_neg_helmet and not has_pos_helmet:
            candidates.append({"type": "NO_HELMET", "box": p["box"], "conf": p["conf"], "pid": pid})

        has_pos_goggles = any(iou(v["box"], head_zone) > 0.1 or in_zone(center(v["box"]), head_zone) for v in pos_goggles)
        has_neg_goggles = any(iou(n["box"], head_zone) > 0.1 or in_zone(center(n["box"]), head_zone) for n in no_goggles)
        if has_neg_goggles and not has_pos_goggles:
            candidates.append({"type": "NO_GOGGLES", "box": p["box"], "conf": p["conf"], "pid": pid})

        has_pos_gloves = any(iou(v["box"], hands_zone) > 0.1 or in_zone(center(v["box"]), hands_zone) for v in pos_gloves)
        has_neg_gloves = any(iou(n["box"], hands_zone) > 0.1 or in_zone(center(n["box"]), hands_zone) for n in no_gloves)
        if has_neg_gloves and not has_pos_gloves:
            candidates.append({"type": "NO_GLOVES", "box": p["box"], "conf": p["conf"], "pid": pid})

        has_pos_boots = any(iou(v["box"], feet_zone) > 0.1 or in_zone(center(v["box"]), feet_zone) for v in pos_boots)
        has_neg_boots = any(iou(n["box"], feet_zone) > 0.1 or in_zone(center(n["box"]), feet_zone) for n in no_boots)
        if has_neg_boots and not has_pos_boots:
            candidates.append({"type": "NO_BOOTS", "box": p["box"], "conf": p["conf"], "pid": pid})

        has_vest = any(iou(v["box"], torso_zone) > 0.1 or in_zone(center(v["box"]), torso_zone) for v in vests)
        # NO_VEST is an INFERRED violation (the model does not predict no_vest)
        if S["check_vest"] and not has_vest:
            candidates.append({"type": "NO_VEST", "box": p["box"], "conf": p["conf"], "pid": pid})

    kept = []
    current_keys = set()

    for v in candidates:
        key = (v["type"], v["pid"])
        current_keys.add(key)
        _streak[key] = _streak.get(key, 0) + 1

        if _streak[key] < S["min_frames"]:
            continue

        if now - _cooldown.get(key, 0) < S["cooldown_sec"]:
            continue

        _cooldown[key] = now
        kept.append(v)

    keys_to_delete = []
    for k in _streak:
        if k not in current_keys:
            _streak[k] -= 1
            if _streak[k] <= 0:
                keys_to_delete.append(k)
    for k in keys_to_delete:
        del _streak[k]

    return kept
