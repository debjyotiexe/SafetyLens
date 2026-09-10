import pytest
from fastapi.testclient import TestClient
from main import app, get_user
from database import init_db, _conn
import config

config.DB_PATH = "test_analytics.db"
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM violations")
        c.execute("DELETE FROM cameras")
        c.execute("DELETE FROM alerts")

    def override_get_user():
        return {"username": "test_user", "role": "viewer"}

    app.dependency_overrides[get_user] = override_get_user
    yield
    app.dependency_overrides.clear()


def seed_test_violations():
    """Seed 10 violations across 3 days, 2 cameras, 3 types. 4 resolved."""
    violations = [
        # Day 1: 2026-09-01
        ("cam_01", "NO_HELMET", 0.92, "snap1.jpg", "2026-09-01 10:15:00", "resolved", "2026-09-01 11:00:00", "admin"),
        ("cam_01", "NO_VEST", 0.88, "snap2.jpg", "2026-09-01 10:30:00", "open", None, None),
        ("cam_02", "NO_HELMET", 0.95, "snap3.jpg", "2026-09-01 14:00:00", "resolved", "2026-09-01 15:00:00", "admin"),
        # Day 2: 2026-09-02
        ("cam_01", "NO_GLOVES", 0.81, "snap4.jpg", "2026-09-02 09:00:00", "open", None, None),
        ("cam_01", "NO_HELMET", 0.90, "snap5.jpg", "2026-09-02 11:20:00", "resolved", "2026-09-02 12:00:00", "admin"),
        ("cam_02", "NO_VEST", 0.85, "snap6.jpg", "2026-09-02 16:45:00", "open", None, None),
        # Day 3: 2026-09-03
        ("cam_01", "NO_HELMET", 0.93, "snap7.jpg", "2026-09-03 08:30:00", "open", None, None),
        ("cam_01", "NO_VEST", 0.87, "snap8.jpg", "2026-09-03 09:10:00", "resolved", "2026-09-03 09:40:00", "admin"),
        ("cam_02", "NO_GLOVES", 0.79, "snap9.jpg", "2026-09-03 13:25:00", "open", None, None),
        ("cam_01", "NO_HELMET", 0.96, "snap10.jpg", "2026-09-03 17:05:00", "open", None, None),
    ]
    with _conn() as c:
        for v in violations:
            c.execute("""
                INSERT INTO violations (camera_id, type, confidence, snapshot, created_at, status, resolved_at, resolved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, v)


def test_analytics_math_verification():
    seed_test_violations()

    res = client.get("/api/analytics/summary?from_date=2026-09-01&to_date=2026-09-03")
    assert res.status_code == 200
    data = res.json()

    kpis = data["kpis"]
    assert kpis["total_violations"] == 10
    assert kpis["resolved_violations"] == 4
    assert kpis["open_violations"] == 6
    assert kpis["resolution_rate"] == 40.0
    assert kpis["busiest_camera"]["camera_id"] == "cam_01"
    assert kpis["busiest_camera"]["count"] == 7

    # Breakdown verification
    breakdown = data["breakdown"]
    type_counts = {b["type"]: b["count"] for b in breakdown["by_type"]}
    assert type_counts == {"NO_HELMET": 5, "NO_VEST": 3, "NO_GLOVES": 2}

    cam_counts = {c["camera_id"]: c["count"] for c in breakdown["by_camera"]}
    assert cam_counts == {"cam_01": 7, "cam_02": 3}


def test_clean_hours_logic():
    # Insert violations across exactly 2 distinct hours in a 24-hour window
    with _conn() as c:
        c.execute("""
            INSERT INTO violations (camera_id, type, confidence, snapshot, created_at, status)
            VALUES 
                ('cam_01', 'NO_HELMET', 0.9, 's1.jpg', '2026-09-05 09:10:00', 'open'),
                ('cam_01', 'NO_HELMET', 0.85, 's2.jpg', '2026-09-05 09:40:00', 'open'),
                ('cam_01', 'NO_VEST', 0.92, 's3.jpg', '2026-09-05 14:15:00', 'resolved')
        """)

    res = client.get("/api/analytics/summary?from_date=2026-09-05%2000:00:00&to_date=2026-09-06%2000:00:00")
    assert res.status_code == 200
    data = res.json()

    # Total hours = 24.0, violation hours = 2 (09 and 14), clean hours = 22.0
    # Score = (22 / 24) * 100 = 91.666... -> 91.7
    assert data["range"]["total_hours"] == 24.0
    assert data["range"]["clean_hours"] == 22.0
    assert data["range"]["violation_hours"] == 2
    assert data["kpis"]["compliance_score"] == 91.7
    assert data["kpis"]["compliance_formula"] == "100 * (clean_hours / total_hours)"


def test_zero_filling_daily_and_hourly():
    # Seed violations on Day 1 and Day 7 only
    with _conn() as c:
        c.execute("""
            INSERT INTO violations (camera_id, type, confidence, snapshot, created_at, status)
            VALUES 
                ('cam_01', 'NO_HELMET', 0.9, 's1.jpg', '2026-09-01 10:00:00', 'open'),
                ('cam_01', 'NO_VEST', 0.85, 's2.jpg', '2026-09-07 14:00:00', 'open')
        """)

    res = client.get("/api/analytics/summary?from_date=2026-09-01&to_date=2026-09-07")
    assert res.status_code == 200
    data = res.json()

    # 1. 7-day trend contains exactly 7 items
    daily = data["trends"]["daily"]
    assert len(daily) == 7
    expected_dates = [f"2026-09-0{i}" for i in range(1, 8)]
    assert [d["date"] for d in daily] == expected_dates
    assert daily[0]["count"] == 1  # 2026-09-01
    assert daily[1]["count"] == 0  # 2026-09-02 (zero-filled)
    assert daily[2]["count"] == 0  # 2026-09-03 (zero-filled)
    assert daily[3]["count"] == 0  # 2026-09-04 (zero-filled)
    assert daily[4]["count"] == 0  # 2026-09-05 (zero-filled)
    assert daily[5]["count"] == 0  # 2026-09-06 (zero-filled)
    assert daily[6]["count"] == 1  # 2026-09-07

    # 2. Hourly trend contains exactly 24 items (00-23)
    hourly = data["trends"]["hourly"]
    assert len(hourly) == 24
    expected_hours = [f"{h:02d}" for h in range(24)]
    assert [h["hour"] for h in hourly] == expected_hours
    hour_map = {h["hour"]: h["count"] for h in hourly}
    assert hour_map["10"] == 1
    assert hour_map["14"] == 1
    assert hour_map["00"] == 0


def test_empty_range():
    res = client.get("/api/analytics/summary?from_date=2025-01-01&to_date=2025-01-02")
    assert res.status_code == 200
    data = res.json()

    kpis = data["kpis"]
    assert kpis["total_violations"] == 0
    assert kpis["open_violations"] == 0
    assert kpis["resolved_violations"] == 0
    assert kpis["resolution_rate"] == 100.0
    assert kpis["compliance_score"] == 100.0
    assert kpis["busiest_camera"] == {"camera_id": "NONE", "count": 0}


def test_reports_generate():
    seed_test_violations()

    # Filter for cam_01 only
    res = client.get("/api/reports/generate?from_date=2026-09-01&to_date=2026-09-03&camera=cam_01")
    assert res.status_code == 200
    data = res.json()

    assert "metadata" in data
    assert data["metadata"]["filters"]["camera"] == "cam_01"
    assert data["metadata"]["generated_by"] == "test_user"

    summary = data["summary"]
    assert summary["total_violations"] == 7
    assert summary["resolved_violations"] == 3
    assert summary["open_violations"] == 4
    assert summary["resolution_rate"] == 42.9

    # Evidence list
    evidence = data["top_evidence"]
    assert len(evidence) <= 10
    assert len(evidence) == 7
    for item in evidence:
        assert item["camera_id"] == "cam_01"
        assert item["snapshot_url"] == f"/snapshots/{item['snapshot']}"


def test_reports_export_csv():
    seed_test_violations()

    res = client.get("/api/reports/export?from_date=2026-09-01&to_date=2026-09-03")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment; filename=safetylens_report.csv" in res.headers["content-disposition"]

    lines = res.text.strip().splitlines()
    assert lines[0] == "id,camera_id,type,confidence,snapshot,created_at,status,resolved_at,resolved_by"
    assert len(lines) == 11  # 1 header line + 10 data lines


def test_auth_required():
    app.dependency_overrides.clear()  # Remove override

    for path in ["/api/analytics/summary", "/api/reports/generate", "/api/reports/export"]:
        res = client.get(path)
        assert res.status_code == 401
