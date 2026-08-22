import time
import config
from compliance import check_compliance, _trackers, _streak, _cooldown, get_person_ids

def setup():
    config.SETTINGS.update(min_frames=1, cooldown_sec=0,
                           person_conf=0.5, gear_conf=0.3)
    _trackers.clear()
    _streak.clear()
    _cooldown.clear()

def test_negative_classes_require_person():
    setup()
    dets = [{"cls": "no_helmet", "conf": 0.9, "box": [120, 110, 180, 170]}]
    assert check_compliance(dets) == []

def test_missing_helmet_explicit():
    setup()
    config.SETTINGS["check_vest"] = False
    dets = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]},
        {"cls": "no_helmet", "conf": 0.9, "box": [120, 110, 180, 170]}
    ]
    assert any(v["type"] == "NO_HELMET" for v in check_compliance(dets))

def test_inferred_missing_vest():
    setup()
    config.SETTINGS["check_vest"] = True
    dets = [{"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]}]
    types = {v["type"] for v in check_compliance(dets)}
    assert types == {"NO_VEST"}

def test_conflict_resolution():
    setup()
    config.SETTINGS["check_vest"] = False
    dets = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]},
        {"cls": "no_helmet", "conf": 0.9, "box": [120, 110, 180, 170]},
        {"cls": "helmet", "conf": 0.9, "box": [120, 110, 180, 170]}
    ]
    # Positive should suppress negative
    assert check_compliance(dets) == []

def test_temporal_confirmation():
    setup()
    config.SETTINGS["min_frames"] = 3
    config.SETTINGS["check_vest"] = True
    dets = [{"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]}]

    assert check_compliance(dets) == [] # Frame 1
    assert check_compliance(dets) == [] # Frame 2
    res = check_compliance(dets)        # Frame 3
    assert len(res) == 1 and res[0]["type"] == "NO_VEST"

def test_cooldown():
    setup()
    config.SETTINGS["min_frames"] = 1
    config.SETTINGS["cooldown_sec"] = 10
    config.SETTINGS["check_vest"] = True
    dets = [{"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]}]

    assert len(check_compliance(dets)) == 1
    assert check_compliance(dets) == [] # Still in cooldown

def test_tracker_stability():
    setup()
    config.SETTINGS["check_vest"] = False
    p1 = {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]}
    p2 = {"cls": "Person", "conf": 0.9, "box": [300, 100, 400, 400]}

    check_compliance([p1, p2])
    assert len(_trackers) == 2

    # Overlap (p1 moves closer to p2, but still overlaps its old self)
    p1_moved = {"cls": "Person", "conf": 0.9, "box": [150, 100, 250, 400]}
    p2_moved = {"cls": "Person", "conf": 0.9, "box": [250, 100, 350, 400]}
    check_compliance([p1_moved, p2_moved])
    assert len(_trackers) == 2

    # One drops out
    check_compliance([p1_moved])
    assert len(_trackers) == 2 # other is preserved with missed count

    # Wait for timeout
    time.sleep(2.1)
    check_compliance([p1_moved])
    assert len(_trackers) == 1
