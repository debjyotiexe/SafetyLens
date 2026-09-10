import os

# Central configuration
SNAPSHOT_DIR = os.environ.get("SNAPSHOT_DIR", "snapshots")
STORAGE_BACKEND = os.environ.get("SL_STORAGE_BACKEND", "local")
SNAPSHOT_RETENTION_DAYS = int(os.environ.get("SL_SNAPSHOT_RETENTION_DAYS", "0"))
TOKEN_TTL_HOURS = int(os.environ.get("SL_TOKEN_TTL_HOURS", "12"))
LOGIN_THROTTLE_LIMIT = int(os.environ.get("SL_LOGIN_THROTTLE_LIMIT", "5"))
LOGIN_THROTTLE_LOCKOUT_SEC = int(os.environ.get("SL_LOGIN_THROTTLE_LOCKOUT_SEC", "60"))
LOGIN_THROTTLE_ENABLED = os.environ.get("SL_LOGIN_THROTTLE_ENABLED", "true").lower() in ("true", "1", "yes")

DB_PATH = os.environ.get("DB_PATH", "safetylens.db")
CAMERA_ID = "cam_01"
CAMERA_FRAME_INTERVAL = 0.1

RELEVANT_CLASSES = {
    # Special class
    "none",

    # Person
    "Person", "person",

    # Positive PPE classes
    "helmet", "Hardhat", "vest", "gloves", "boots", "goggles",

    # Negative PPE classes (NOTE: Custom model does NOT output no_vest)
    "no_helmet", "NO-Hardhat", "no_goggle", "no_gloves", "no_boots"
}

VIOLATION_CLASSES = {
    "NO-Hardhat": "NO_HELMET",
    "no_helmet": "NO_HELMET",
    "no_goggle": "NO_GOGGLES",
    "no_gloves": "NO_GLOVES",
    "no_boots": "NO_BOOTS",
    # NO_VEST is inferred programmatically, not mapped from a negative class.
}

# Switchable models (Settings console)
MODEL_OPTIONS = {
    "v0-hardhat": {"path": "models/best.pt", "name": "Basic Hardhat Model"},
    "v1-custom": {"path": "models/safetylens_v1.pt", "name": "SafetyLens Custom PPE"},
}

# Live-tunable runtime settings (Settings console)
SETTINGS = {
    "confidence": 0.3,
    "negative_confidence": 0.15,
    "person_conf": 0.5,
    "gear_conf": 0.3,
    "cooldown_sec": 30,
    "min_frames": 3,
    "check_vest": True,
    "model": "v1-custom",
}

# Alert Dispatcher settings
ALERT_SETTINGS = {
    "log": {"enabled": True},
    "email": {
        "enabled": False,
        "smtp_host": os.environ.get("SL_SMTP_HOST", ""),
        "smtp_port": int(os.environ.get("SL_SMTP_PORT", "587")),
        "from_addr": os.environ.get("SL_SMTP_FROM", ""),
        "to_addrs": os.environ.get("SL_SMTP_TO", ""),
        "username": os.environ.get("SL_SMTP_USER", ""),
        "password": os.environ.get("SL_SMTP_PASS", ""),
    },
    "webhook": {
        "enabled": False,
        "url": os.environ.get("SL_WEBHOOK_URL", ""),
    },
}
