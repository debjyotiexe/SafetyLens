# Central configuration
SNAPSHOT_DIR = "snapshots"
DB_PATH = "safetylens.db"
CAMERA_ID = "cam_01"

RELEVANT_CLASSES = {"Person", "person", "helmet", "vest", "no_helmet",
                    "Hardhat", "NO-Hardhat"}

VIOLATION_CLASSES = {
    "NO-Hardhat": "NO_HELMET",
    "no_helmet": "NO_HELMET",
}

# Switchable models (Settings console)
MODEL_OPTIONS = {
    "v0-hardhat": "models/best.pt",
    "v1-custom": "models/safetylens_v1.pt",
}

# Live-tunable runtime settings (Settings console)
SETTINGS = {
    "confidence": 0.3,
    "person_conf": 0.5,
    "gear_conf": 0.3,
    "cooldown_sec": 30,
    "min_frames": 3,
    "check_vest": True,
    "model": "v1-custom",
}