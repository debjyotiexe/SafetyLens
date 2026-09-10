import cv2
import time
import os
import base64
from ultralytics import YOLO
from config import SETTINGS, RELEVANT_CLASSES, MODEL_OPTIONS
from compliance import check_compliance, _streak
import database

print("Loading model...", flush=True)
model = YOLO(MODEL_OPTIONS["v1-custom"]["path"])
RELEVANT_IDS = [i for i, name in model.names.items() if name in RELEVANT_CLASSES]

# Update settings
SETTINGS["min_frames"] = 3
SETTINGS["cooldown_sec"] = 30
SETTINGS["check_vest"] = True
SETTINGS["confidence"] = 0.3
SETTINGS["negative_confidence"] = 0.15

cap = cv2.VideoCapture("/assets/13186865_1920_1080_60fps.mp4")
if not cap.isOpened():
    print("Failed to open video", flush=True)
    exit(1)

frame_count = 0
raw_no_helmet_count = 0
accepted_no_helmet_count = 0
final_confirmed_violations = set()

print("Processing video simulating browser (640x480, 5 FPS)...", flush=True)
while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    # Browser sends every 200ms. Video is 60fps. 60fps * 0.2s = 12 frames.
    if frame_count % 12 != 0:
        continue

    # Simulate browser frame skip
    # (Removed resize/compression to isolate cause)

    inference_conf = min(SETTINGS["confidence"], SETTINGS.get("negative_confidence", 0.15))
    results = model.predict(frame, conf=inference_conf, classes=RELEVANT_IDS, verbose=False)
    detections = [
        {"cls": model.names[int(b.cls[0])],
         "conf": float(b.conf[0]),
         "box": list(map(int, b.xyxy[0]))}
        for b in results[0].boxes
    ]

    for d in detections:
        if d["cls"] in ("no_helmet", "NO-Hardhat"):
            raw_no_helmet_count += 1
            if d["conf"] >= SETTINGS.get("negative_confidence", 0.15):
                accepted_no_helmet_count += 1
        
    violations = check_compliance(detections)
    for v in violations:
        final_confirmed_violations.add(v["type"])

print("--- RESULTS ---")
print(f"Raw no_helmet detections: {raw_no_helmet_count}")
print(f"Accepted no_helmet detections: {accepted_no_helmet_count}")
print("Violations surviving temporal confirmation:")
for type_ in sorted(list(final_confirmed_violations)):
    print(f"   - {type_}")
