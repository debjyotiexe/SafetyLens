import cv2
import time
import os
import base64
from ultralytics import YOLO
from config import SETTINGS, RELEVANT_CLASSES, MODEL_OPTIONS
from compliance import check_compliance, _streak
import database

print("Loading model...")
model = YOLO(MODEL_OPTIONS["v1-custom"]["path"])
RELEVANT_IDS = [i for i, name in model.names.items() if name in RELEVANT_CLASSES]

# Update settings
SETTINGS["min_frames"] = 3
SETTINGS["cooldown_sec"] = 30
SETTINGS["check_vest"] = True
SETTINGS["confidence"] = 0.3

# Setup DB
database.DB_PATH = "safetylens_val.db"
if os.path.exists(database.DB_PATH):
    try: os.remove(database.DB_PATH)
    except: pass
database.init_db()

cap = cv2.VideoCapture("/assets/13186865_1920_1080_60fps.mp4")
if not cap.isOpened():
    print("Failed to open video")
    exit(1)

frame_count = 0
all_raw_classes = set()
geometric_survivals = set()
final_confirmed_violations = set()
associations_by_pid = {}
raw_no_helmet_count = 0
accepted_no_helmet_count = 0

print("Processing video...")
while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    # Process every 5th frame for speed
    if frame_count % 5 != 0:
        continue

    inference_conf = min(SETTINGS["confidence"], SETTINGS.get("negative_confidence", 0.20))
    results = model.predict(frame, conf=inference_conf, classes=RELEVANT_IDS, verbose=False)
    detections = [
        {"cls": model.names[int(b.cls[0])],
         "conf": float(b.conf[0]),
         "box": list(map(int, b.xyxy[0]))}
        for b in results[0].boxes
    ]

    for d in detections:
        all_raw_classes.add(d["cls"])
        if d["cls"] in ("no_helmet", "NO-Hardhat"):
            raw_no_helmet_count += 1
            if d["conf"] >= SETTINGS.get("negative_confidence", 0.20):
                accepted_no_helmet_count += 1
        
    violations = check_compliance(detections)
    
    # Track geometric survivals by looking at the active streak keys
    for key, count in _streak.items():
        if count > 0:
            type_, pid = key
            geometric_survivals.add(type_)
            if pid not in associations_by_pid:
                associations_by_pid[pid] = {}
            if type_ not in associations_by_pid[pid]:
                associations_by_pid[pid][type_] = count
            else:
                associations_by_pid[pid][type_] = max(associations_by_pid[pid][type_], count)

    for v in violations:
        final_confirmed_violations.add(v["type"])
        snap_name = f"{v['type']}_PID{v['pid']}_{frame_count}.jpg"
        snap_path = os.path.join(SETTINGS.get("SNAPSHOT_DIR", "snapshots"), snap_name)
        img = frame.copy()
        x1, y1, x2, y2 = map(int, v["box"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(img, v["type"], (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        os.makedirs(os.path.dirname(snap_path), exist_ok=True)
        cv2.imwrite(snap_path, img)
        database.log_violation(v["type"], v["conf"], snap_name, "cam_01")

print("--- RESULTS ---")
print(f"0. Raw no_helmet detections: {raw_no_helmet_count}")
print(f"   Accepted no_helmet detections (conf >= {SETTINGS.get('negative_confidence', 0.20)}): {accepted_no_helmet_count}")

print("1. Raw YOLO classes observed:")
for cls in sorted(list(all_raw_classes)):
    print(f"   - {cls}")

print("\n2. Detections actually associated with Persons (longest streak by PID):")
for pid, classes in associations_by_pid.items():
    print(f"   - PID {pid}: {classes}")

print("\n3. Detections surviving geometric zone checks:")
for type_ in sorted(list(geometric_survivals)):
    print(f"   - {type_}")

print("\n4. Violations surviving temporal confirmation:")
for type_ in sorted(list(final_confirmed_violations)):
    print(f"   - {type_}")

stats = database.get_stats()
print("\n5. Final dashboard KPI values after the video completes:")
print(f"   - Total violations today: {stats['today']}")
print(f"   - All-time total violations: {stats['total']}")
print("   - By Type:")
for row in stats["by_type"]:
    print(f"     * {row[0]}: {row[1]}")
