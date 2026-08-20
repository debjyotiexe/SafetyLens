import config
from compliance import check_compliance

def setup():
    config.SETTINGS.update(min_frames=1, cooldown_sec=0,
                           person_conf=0.5, gear_conf=0.3)

def test_direct_missing_helmet():
    setup()
    dets = [{"cls": "no_helmet", "conf": 0.9, "box": [10, 10, 50, 50]}]
    assert any(v["type"] == "NO_HELMET" for v in check_compliance(dets))

def test_fully_compliant_worker():
    setup()
    config.SETTINGS["check_vest"] = True
    dets = [
        {"cls": "Person", "conf": 0.9, "box": [100, 100, 200, 400]},
        {"cls": "helmet", "conf": 0.9, "box": [110, 105, 190, 160]},
        {"cls": "vest",   "conf": 0.9, "box": [110, 190, 190, 300]},
    ]
    assert check_compliance(dets) == []

def test_worker_missing_everything():
    setup()
    config.SETTINGS["check_vest"] = True
    dets = [{"cls": "Person", "conf": 0.9, "box": [300, 300, 400, 700]}]
    types = {v["type"] for v in check_compliance(dets)}
    assert types == {"NO_HELMET", "NO_VEST"}

def test_vest_check_disabled():
    setup()
    config.SETTINGS["check_vest"] = False
    dets = [{"cls": "Person", "conf": 0.9, "box": [500, 500, 600, 900]}]
    types = {v["type"] for v in check_compliance(dets)}
    assert types == {"NO_HELMET"}