import cv2
from ultralytics import YOLO
import time
from config import SETTINGS, RELEVANT_CLASSES
import compliance

model = YOLO("models/safetylens_v1.pt")
cap = cv2.VideoCapture("/assets/13186865_1920_1080_60fps.mp4")

target_classes = ["no_helmet", "no_gloves", "no_boots", "no_goggle"]

metrics = {c: {
    "raw_count": 0,
    "confs": [],
    "survive_conf": 0,
    "associated_person": 0,
    "pass_zone": 0,
    "longest_streak": {},
    "reach_min_frames": 0,
    "committed_violations": 0
} for c in target_classes}

rejection_reasons = {c: [] for c in target_classes}

frame_idx = 0
RELEVANT_IDS = [k for k, v in model.names.items() if v in RELEVANT_CLASSES]

print("Starting diagnostic...")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_idx += 1
    if frame_idx % 5 != 0:
        continue
        
    inference_conf = 0.05 # let everything through to observe raw detections
    results = model.predict(frame, conf=inference_conf, classes=RELEVANT_IDS, verbose=False)
    
    detections = []
    for b in results[0].boxes:
        c_name = model.names[int(b.cls[0])]
        detections.append({"cls": c_name, "conf": float(b.conf[0]), "box": b.xyxy[0].tolist()})
        
    for d in detections:
        if d["cls"] in target_classes:
            metrics[d["cls"]]["raw_count"] += 1
            metrics[d["cls"]]["confs"].append(d["conf"])
            if d["conf"] < SETTINGS.get("negative_confidence", 0.20):
                if len(rejection_reasons[d["cls"]]) < 5:
                    rejection_reasons[d["cls"]].append(f"Rejected by confidence ({d['conf']:.3f} < 0.20)")
            
    neg_conf = SETTINGS.get("negative_confidence", 0.20)
    survived = [d for d in detections if d["conf"] >= (neg_conf if d["cls"] in target_classes else SETTINGS["confidence"])]
    
    for d in survived:
        if d["cls"] in target_classes:
            metrics[d["cls"]]["survive_conf"] += 1

    persons = [d for d in survived if d["cls"] in ("Person", "person")]
    box_to_pid = compliance.get_person_ids([p["box"] for p in persons])
    
    for tc in target_classes:
        t_dets = [d for d in survived if d["cls"] == tc]
        for t in t_dets:
            assoc = False
            pass_z = False
            for i, p in enumerate(persons):
                x1, y1, x2, y2 = p["box"]
                w, h = x2 - x1, y2 - y1
                
                # Check general association
                if compliance.iou(t["box"], p["box"]) > 0 or compliance.in_zone(compliance.center(t["box"]), p["box"]):
                    assoc = True
                    
                head_zone = [x1, y1 - 0.1*h, x2, y1 + 0.3*h]
                hands_zone = [x1 - 0.3*w, y1 + 0.4*h, x2 + 0.3*w, y2]
                feet_zone = [x1 - 0.2*w, y1 + 0.7*h, x2 + 0.2*w, y2 + 0.2*h]
                
                if tc in ("no_helmet", "no_goggle"):
                    zone = head_zone
                elif tc == "no_gloves":
                    zone = hands_zone
                else:
                    zone = feet_zone
                    
                if compliance.iou(t["box"], zone) > 0.1 or compliance.in_zone(compliance.center(t["box"]), zone):
                    pass_z = True
            
            if assoc:
                metrics[tc]["associated_person"] += 1
            if pass_z:
                metrics[tc]["pass_zone"] += 1
                
            if not pass_z:
                if len(rejection_reasons[tc]) < 10:
                    if assoc:
                        rejection_reasons[tc].append(f"Wrong zone (Conf: {t['conf']:.2f})")
                    else:
                        rejection_reasons[tc].append(f"Wrong person/no association (Conf: {t['conf']:.2f})")

    # Check for streak reset/cooldown via standard compliance logic
    prev_streak = compliance._streak.copy()
    violations = compliance.check_compliance(survived)
    
    # Check if a streak was reset
    for key, old_count in prev_streak.items():
        if key not in compliance._streak and old_count > 0:
            vtype, pid = key
            vmap = {"NO_HELMET": "no_helmet", "NO_GOGGLES": "no_goggle", "NO_GLOVES": "no_gloves", "NO_BOOTS": "no_boots"}
            if vtype in vmap and len(rejection_reasons[vmap[vtype]]) < 15:
                rejection_reasons[vmap[vtype]].append(f"Streak reset at count {old_count} for PID {pid}")
    
    for key, count in compliance._streak.items():
        vtype, pid = key
        vmap = {"NO_HELMET": "no_helmet", "NO_GOGGLES": "no_goggle", "NO_GLOVES": "no_gloves", "NO_BOOTS": "no_boots"}
        if vtype in vmap:
            tc = vmap[vtype]
            metrics[tc]["longest_streak"][pid] = max(metrics[tc]["longest_streak"].get(pid, 0), count)
            if count == SETTINGS["min_frames"] and prev_streak.get(key, 0) == SETTINGS["min_frames"] - 1:
                metrics[tc]["reach_min_frames"] += 1
                
    for v in violations:
        vmap = {"NO_HELMET": "no_helmet", "NO_GOGGLES": "no_goggle", "NO_GLOVES": "no_gloves", "NO_BOOTS": "no_boots"}
        if v["type"] in vmap:
            metrics[vmap[v["type"]]]["committed_violations"] += 1
            if v["type"] == "NO_HELMET":
                print(f"NO_HELMET VIOLATION at frame {frame_idx}, PID {v['pid']}")
                
print("\n--- DIAGNOSTIC RESULTS ---")
for tc in target_classes:
    m = metrics[tc]
    print(f"\n[{tc.upper()}]")
    print(f"1. Raw YOLO detection count: {m['raw_count']}")
    if m['raw_count'] > 0:
        print(f"2. Confidence - Min: {min(m['confs']):.3f}, Mean: {sum(m['confs'])/len(m['confs']):.3f}, Max: {max(m['confs']):.3f}")
    else:
        print("2. Confidence - N/A")
    print(f"3. Number surviving negative_confidence=0.20: {m['survive_conf']}")
    print(f"4. Number associated with a Person: {m['associated_person']}")
    print(f"5. Number passing geometric zone association: {m['pass_zone']}")
    print(f"6. Longest consecutive streak per PID: {m['longest_streak']}")
    print(f"7. Number reaching min_frames=3: {m['reach_min_frames']}")
    print(f"8. Number actually committed as violations: {m['committed_violations']}")
    print("Examples of rejected detections / issues:")
    for r in rejection_reasons[tc]:
        print("  -", r)
