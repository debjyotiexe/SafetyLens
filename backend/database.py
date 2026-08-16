import sqlite3, hashlib, secrets
from config import DB_PATH

def _conn():
    return sqlite3.connect(DB_PATH)

def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()

def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            type TEXT NOT NULL,
            confidence REAL,
            snapshot TEXT,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            violation_id INTEGER REFERENCES violations(id),
            channel TEXT DEFAULT 'app',
            sent_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        """)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for u, p, r in [("admin", "admin123", "admin"), ("viewer", "view123", "viewer")]:
                salt = secrets.token_hex(8)
                c.execute("INSERT INTO users (username,password_hash,salt,role) VALUES (?,?,?,?)",
                          (u, hash_pw(p, salt), salt, r))

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
        by_type = c.execute("SELECT type, COUNT(*) FROM violations GROUP BY type").fetchall()
        hourly = c.execute("""
            SELECT strftime('%H', created_at), COUNT(*) FROM violations
            WHERE date(created_at)=date('now','localtime')
            GROUP BY 1 ORDER BY 1""").fetchall()
    return {"total": total, "today": today, "by_type": by_type, "hourly": hourly}

# ---------- auth ----------
def verify_login(username, password):
    with _conn() as c:
        row = c.execute("SELECT password_hash, salt, role FROM users WHERE username=?",
                        (username,)).fetchone()
    if not row or row[0] != hash_pw(password, row[1]):
        return None
    token = secrets.token_hex(24)
    with _conn() as c:
        c.execute("INSERT INTO tokens (token, username, role) VALUES (?,?,?)",
                  (token, username, row[2]))
    return {"token": token, "username": username, "role": row[2]}

def check_token(token):
    if not token:
        return None
    with _conn() as c:
        row = c.execute("SELECT username, role FROM tokens WHERE token=?", (token,)).fetchone()
    return {"username": row[0], "role": row[1]} if row else None