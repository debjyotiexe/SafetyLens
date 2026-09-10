import cv2
import time
import os
from ultralytics import YOLO
from config import SETTINGS, RELEVANT_CLASSES, MODEL_OPTIONS
import compliance

print("Loading model...")
model = YOLO(MODEL_OPTIONS["v1-custom"]["path"])
RELEVANT_IDS = [i for i, name in model.names.items() if name in RELEVANT_CLASSES]
SETTINGS["min_frames"] = 3
SETTINGS["person_conf"] = 0.5
SETTINGS["gear_conf"] = 0.3

cap = cv2.VideoCapture("/assets/13186865_1920_1080_60fps.mp4")

frame_idx = 0
total_raw_no_helmet = 0
frames_with_no_helmet = set()

# To track no_helmet candidates
tracking_log = []

print("Processing video (skipping frames to maintain decent speed)...")
compliance._trackers.clear()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_idx += 1
    if frame_idx % 3 != 0:
        continue

    results = model.predict(frame, conf=0.1, classes=RELEVANT_IDS, verbose=False) # lowered conf to see if D is the cause
    detections = [
        {"cls": model.names[int(b.cls[0])], "conf": float(b.conf[0]), "box": list(map(int, b.xyxy[0]))}
        for b in results[0].boxes
    ]
    
    no_helmets_all = [d for d in detections if d["cls"] in ("no_helmet", "NO-Hardhat")]
    
    # Filter by conf threshold
    no_helmets_valid = [nh for nh in no_helmets_all if nh["conf"] >= SETTINGS["gear_conf"]]
    
    total_raw_no_helmet += len(no_helmets_all)
    if no_helmets_all:
        frames_with_no_helmet.add(frame_idx)
        
    persons = [d for d in detections if d["cls"] in ("Person", "person") and d["conf"] >= SETTINGS["person_conf"]]
    box_to_pid = compliance.get_person_ids([p["box"] for p in persons])
    
    # Geometric checks
    for i, p in enumerate(persons):
        pid = box_to_pid[i]
        x1, y1, x2, y2 = p["box"]
        w = x2 - x1; h = y2 - y1
        head_zone = [x1, y1 - 0.1*h, x2, y1 + 0.3*h]
        
        person_log = {
            "frame": frame_idx,
            "pid": pid,
            "p_box": p["box"],
            "head_zone": head_zone,
            "no_helmet_found": False,
            "conf_fail": False,
            "geom_fail": False,
            "nh_box": None,
            "nh_conf": 0.0,
            "iou_val": 0.0,
            "in_zn": False
        }
        
        # Did we find a no_helmet that associates?
        best_geom_score = -1
        best_nh = None
        best_iou = 0
        best_in_zn = False
        
        # Try ALL no_helmets for this person to diagnose C, D
        for nh in no_helmets_all:
            c = compliance.center(nh["box"])
            in_zn = compliance.in_zone(c, head_zone)
            iou_val = compliance.iou(nh["box"], head_zone)
            score = max(iou_val, 1.0 if in_zn else 0.0)
            
            if score > best_geom_score:
                best_geom_score = score
                best_nh = nh
                best_iou = iou_val
                best_in_zn = in_zn
                
        if best_nh:
            person_log["nh_box"] = best_nh["box"]
            person_log["nh_conf"] = best_nh["conf"]
            person_log["iou_val"] = best_iou
            person_log["in_zn"] = best_in_zn
            
            if best_geom_score > 0.1 or best_in_zn:
                if best_nh["conf"] >= SETTINGS["gear_conf"]:
                    person_log["no_helmet_found"] = True
                else:
                    person_log["conf_fail"] = True
            else:
                person_log["geom_fail"] = True
                
        tracking_log.append(person_log)

print("--- DIAGNOSTIC RESULTS ---")
print(f"1. Total raw `no_helmet` detections (even low conf): {total_raw_no_helmet}")
print(f"2. Number of frames containing `no_helmet`: {len(frames_with_no_helmet)}")

# Group by PID
by_pid = {}
for log in tracking_log:
    pid = log["pid"]
    if pid not in by_pid:
        by_pid[pid] = []
    by_pid[pid].append(log)

print("\n3-9. Streaks and Associations:")
for pid, logs in by_pid.items():
    # Only report PIDs that had AT LEAST ONE no_helmet attempt (either conf fail, geom fail, or success)
    if not any(l["nh_box"] is not None for l in logs):
        continue
        
    print(f"\nPID {pid}:")
    
    current_streak = 0
    max_streak = 0
    longest_streak_logs = []
    current_streak_logs = []
    
    conf_fails = 0
    geom_fails = 0
    total_matches = 0
    
    for l in logs:
        if l["no_helmet_found"]:
            current_streak += 1
            current_streak_logs.append(l)
            total_matches += 1
            if current_streak > max_streak:
                max_streak = current_streak
                longest_streak_logs = list(current_streak_logs)
        else:
            current_streak = 0
            current_streak_logs = []
            if l["conf_fail"]: conf_fails += 1
            if l["geom_fail"]: geom_fails += 1
            
    print(f"  - Longest consecutive NO_HELMET streak: {max_streak} frames")
    print(f"  - Total successful associations: {total_matches}")
    print(f"  - Times association failed due to low confidence (< {SETTINGS['gear_conf']}): {conf_fails}")
    print(f"  - Times association failed due to geometric mismatch: {geom_fails}")
    
    if max_streak > 0:
        example = longest_streak_logs[0]
        print(f"  - Example frame from longest streak (Frame {example['frame']}):")
        print(f"      Person Box: {example['p_box']}")
        print(f"      Head Zone: {[int(x) for x in example['head_zone']]}")
        print(f"      no_helmet Box: {example['nh_box']}")
        print(f"      Confidence: {example['nh_conf']:.2f}")
        print(f"      IoU with Head Zone: {example['iou_val']:.2f}")
        print(f"      Center in Head Zone: {example['in_zn']}")
    elif any(l["geom_fail"] for l in logs):
        # Find one geom fail example
        example = next(l for l in logs if l["geom_fail"])
        print(f"  - Example GEOMETRIC FAIL (Frame {example['frame']}):")
        print(f"      Person Box: {example['p_box']}")
        print(f"      Head Zone: {[int(x) for x in example['head_zone']]}")
        print(f"      no_helmet Box: {example['nh_box']}")
        print(f"      Confidence: {example['nh_conf']:.2f}")
        print(f"      IoU with Head Zone: {example['iou_val']:.2f}")
        print(f"      Center in Head Zone: {example['in_zn']}")

print("\n10. Conclusion for NO_HELMET failing temporal confirmation:")
if total_raw_no_helmet == 0:
    print("A. YOLO itself is producing ZERO no_helmet detections.")
else:
    print("Check the streak data above. If streaks are < 3, temporal confirmation resets.")
