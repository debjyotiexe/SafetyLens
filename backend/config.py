# Central configuration
MODEL_PATH = "runs/detect/models/trained/safetylens_v1-3/weights/best.pt"
CONFIDENCE = 0.3        # raw detection threshold — look HARD for gear
PERSON_CONF = 0.5       # person must be this confident to trigger checks
GEAR_CONF = 0.3         # gear presence check threshold
COOLDOWN_SEC = 30
SNAPSHOT_DIR = "snapshots"
DB_PATH = "safetylens.db"
CAMERA_ID = "cam_01"
CHECK_VEST = True       # set False to disable vest checks (demo emergency switch)
MIN_FRAMES = 3  
RELEVANT_CLASSES = {"Person", "person", "helmet", "vest", "no_helmet",
                    "Hardhat", "NO-Hardhat"}

VIOLATION_CLASSES = {
    "NO-Hardhat": "NO_HELMET",
    "no_helmet": "NO_HELMET",
}