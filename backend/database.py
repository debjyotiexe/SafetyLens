import sqlite3
from config import DB_PATH

def _conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS violations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id   TEXT NOT NULL,
            type        TEXT NOT NULL,
            confidence  REAL,
            snapshot    TEXT,
            created_at  DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_id INTEGER REFERENCES violations(id),
            channel      TEXT DEFAULT 'app',
            sent_at      DATETIME DEFAULT (datetime('now','localtime'))
        );
        """)

def log_violation(vtype, conf, snapshot, camera_id):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO violations (camera_id, type, confidence, snapshot) VALUES (?,?,?,?)",
            (camera_id, vtype, conf, snapshot))
        c.execute("INSERT INTO alerts (violation_id) VALUES (?)", (cur.lastrowid,))
        return cur.lastrowid

def get_stats():
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
        today = c.execute(
            "SELECT COUNT(*) FROM violations WHERE date(created_at)=date('now','localtime')").fetchone()[0]
        by_type = c.execute(
            "SELECT type, COUNT(*) FROM violations GROUP BY type").fetchall()
        hourly = c.execute("""
            SELECT strftime('%H', created_at), COUNT(*) FROM violations
            WHERE date(created_at)=date('now','localtime')
            GROUP BY 1 ORDER BY 1""").fetchall()
    return {"total": total, "today": today, "by_type": by_type, "hourly": hourly}