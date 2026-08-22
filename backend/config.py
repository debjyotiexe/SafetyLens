# Central configuration
SNAPSHOT_DIR = "snapshots"
DB_PATH = "safetylens.db"
CAMERA_ID = "cam_01"

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
