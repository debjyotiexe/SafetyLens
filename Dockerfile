# ---------- SafetyLens AI ----------
FROM python:3.11-slim

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libxcb1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# CPU PyTorch
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y opencv-python opencv-contrib-python || true \
    && pip install --no-cache-dir --force-reinstall opencv-python-headless

# Backend source
COPY backend/ /app/backend/

# Frontend
COPY frontend/ /app/frontend/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]