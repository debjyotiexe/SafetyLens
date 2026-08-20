# ---------- SafetyLens AI — production image (CPU inference) ----------
FROM python:3.11-slim

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (small image). GPU hosts: use nvidia runtime + cu wheels.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Starter model baked in at build time (custom v1 arrives via local models/ copy)
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download('keremberke/yolov8m-hard-hat-detection', 'best.pt', local_dir='models')"

COPY backend/ .
COPY frontend/ /app/frontend/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]