import pytest
import time
from compliance import check_compliance, _streak, _cooldown, _trackers
from config import SETTINGS

@pytest.fixture(autouse=True)
def reset_state():
    _streak.clear()
    _cooldown.clear()
    _trackers.clear()
    
    # Set known config
    SETTINGS["confidence"] = 0.30
    SETTINGS["negative_confidence"] = 0.15
    SETTINGS["person_conf"] = 0.50
    SETTINGS["min_frames"] = 3
    SETTINGS["cooldown_sec"] = 30
    SETTINGS["check_vest"] = True

def test_negative_detection_thresholds():
    # 0.14 should be rejected (negative_confidence=0.15)
    dets_low = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 300]},
        {"cls": "no_helmet", "conf": 0.14, "box": [120, 100, 180, 140]} # head zone
    ]
    # Feed 3 times to satisfy min_frames if it were accepted
    for _ in range(3):
        violations = check_compliance(dets_low)
        time.sleep(0.01)
        
    # Expect only NO_VEST, NO_GLOVES, NO_BOOTS, NO_GOGGLES, but NO NO_HELMET
    assert not any(v["type"] == "NO_HELMET" for v in violations)

    _streak.clear()
    _trackers.clear()

    # 0.16 should be accepted (negative_confidence=0.15)
    dets_high = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 300]},
        {"cls": "no_helmet", "conf": 0.16, "box": [120, 100, 180, 140]}
    ]
    for _ in range(3):
        violations = check_compliance(dets_high)
        time.sleep(0.01)
        
    assert any(v["type"] == "NO_HELMET" for v in violations)

def test_positive_detection_thresholds():
    # If confidence=0.30, a positive detection at 0.25 is REJECTED.
    # Therefore, the system will assume NO_HELMET if there is a valid no_helmet detection
    # OR if it's an inferred violation like NO_VEST, it will trigger because the vest isn't valid.
    
    # Test NO_VEST triggering when vest is 0.25
    dets_low = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 300]},
        {"cls": "vest", "conf": 0.25, "box": [110, 150, 190, 250]} # torso zone
    ]
    
    for _ in range(3):
        violations = check_compliance(dets_low)
        time.sleep(0.01)
        
    # Since vest was rejected (0.25 < 0.30), NO_VEST should trigger
    assert any(v["type"] == "NO_VEST" for v in violations)
    
    _streak.clear()
    _trackers.clear()
    
    # Test NO_VEST NOT triggering when vest is 0.31
    dets_high = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 300]},
        {"cls": "vest", "conf": 0.31, "box": [110, 150, 190, 250]}
    ]
    
    for _ in range(3):
        violations = check_compliance(dets_high)
        time.sleep(0.01)
        
    # Since vest was accepted (0.31 > 0.30), NO_VEST should NOT trigger
    assert not any(v["type"] == "NO_VEST" for v in violations)
