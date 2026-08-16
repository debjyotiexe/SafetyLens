from ultralytics import YOLO

# Pre-trained hard-hat detection model (downloads automatically, ~50 MB)
MODEL_ID = "D:/SafetyLens/backend/models/best.pt"

model = YOLO(MODEL_ID)
print("Model loaded. Classes:", model.names)

# Run on every image in the assets folder
results = model.predict("D:/SafetyLens/assets", save=True, conf=0.4)

for r in results:
    print(f"\nImage: {r.path}")
    for b in r.boxes:
        cls = model.names[int(b.cls[0])]
        conf = float(b.conf[0])
        print(f"   {cls}: {conf:.2f}")

print("\n✅ Annotated images saved to: D:/SafetyLens/backend/runs/detect/predict/")