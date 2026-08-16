from ultralytics import YOLO

# THIS IS THE MAGIC FIX FOR WINDOWS:
if __name__ == '__main__':
    model = YOLO("yolov8n.pt")   # starting point: pretrained nano model

    model.train(
        data="construction-ppe.yaml",   # auto-downloads dataset (~180 MB)
        epochs=60,
        imgsz=640,
        batch=16,
        device=0,          # your RTX 4060
        patience=15,       # early stopping if no improvement
        project="models/trained",
        name="safetylens_v1",
    )

    print("\n✅ TRAINING COMPLETE — best weights saved to models/trained/safetylens_v1/weights/best.pt")