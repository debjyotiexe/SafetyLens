import sqlite3, hashlib, secrets, csv, io, hmac, time
import config

def _conn():
    return sqlite3.connect(config.DB_PATH, timeout=30.0, check_same_thread=False)

_login_attempts = {}

def hash_pw(pw, salt):
    return hashlib.sha256((salt + pw).encode()).hexdigest()

def hash_pw_pbkdf2(pw: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"pbkdf2${salt}${derived}"

def verify_pw(pw: str, stored_hash: str, salt: str) -> tuple[bool, bool]:
    if stored_hash.startswith("pbkdf2$"):
        parts = stored_hash.split("$")
        if len(parts) != 3:
            return False, False
        hash_salt = parts[1]
        expected_hash = parts[2]
        computed = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), hash_salt.encode("utf-8"), 100000).hex()
        if hmac.compare_digest(computed, expected_hash):
            return True, False
        return False, False
    else:
        computed = hashlib.sha256((salt + pw).encode()).hexdigest()
        if hmac.compare_digest(computed, stored_hash):
            return True, True
        return False, False

def upgrade_pw(username: str, pw: str):
    new_salt = secrets.token_hex(16)
    new_hash = hash_pw_pbkdf2(pw, new_salt)
    with _conn() as c:
        c.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                  (new_hash, new_salt, username))

def is_account_locked(username: str) -> tuple[bool, int]:
    if not getattr(config, "LOGIN_THROTTLE_ENABLED", True):
        return False, 0
    entry = _login_attempts.get(username)
    if not entry:
        return False, 0
    now = time.time()
    if entry.get("locked_until", 0) > now:
        remaining = int(entry["locked_until"] - now)
        return True, max(1, remaining)
    return False, 0

def record_login_failure(username: str):
    if not getattr(config, "LOGIN_THROTTLE_ENABLED", True):
        return
    now = time.time()
    entry = _login_attempts.setdefault(username, {"failures": 0, "locked_until": 0})
    if entry["locked_until"] <= now:
        if entry["locked_until"] > 0:
            entry["failures"] = 0
            entry["locked_until"] = 0
    entry["failures"] += 1
    limit = getattr(config, "LOGIN_THROTTLE_LIMIT", 5)
    if entry["failures"] >= limit:
        lockout_sec = getattr(config, "LOGIN_THROTTLE_LOCKOUT_SEC", 60)
        entry["locked_until"] = now + lockout_sec

def record_login_success(username: str):
    if username in _login_attempts:
        del _login_attempts[username]

def reset_throttling():
    _login_attempts.clear()

def table_columns(table_name: str) -> set[str]:
    with _conn() as c:
        return {row[1] for row in c.execute(f"PRAGMA table_info({table_name})").fetchall()}

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
        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            name TEXT,
            type TEXT,
            uri TEXT,
            status TEXT DEFAULT 'offline',
            error_msg TEXT,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        """)

        # Robust migration for violations table
        v_cols = {row[1] for row in c.execute("PRAGMA table_info(violations)").fetchall()}
        if "status" not in v_cols:
            c.execute("ALTER TABLE violations ADD COLUMN status TEXT DEFAULT 'open'")
        if "resolved_at" not in v_cols:
            c.execute("ALTER TABLE violations ADD COLUMN resolved_at DATETIME")
        if "resolved_by" not in v_cols:
            c.execute("ALTER TABLE violations ADD COLUMN resolved_by TEXT")

        # Robust migration for users table
        u_cols = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        if "is_active" not in u_cols:
            c.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "email" not in u_cols:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "created_at" not in u_cols:
            # SQLite ADD COLUMN does not support non-constant default expressions
            c.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            c.execute("UPDATE users SET created_at = datetime('now','localtime') WHERE created_at IS NULL OR created_at = ''")

        # Backfill any existing users with null or empty created_at
        c.execute("UPDATE users SET created_at = datetime('now','localtime') WHERE created_at IS NULL OR created_at = ''")

        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for u, p, r in [("admin", "admin123", "admin"), ("viewer", "view123", "viewer")]:
                salt = secrets.token_hex(16)
                pw_hash = hash_pw_pbkdf2(p, salt)
                c.execute("INSERT INTO users (username,password_hash,salt,role,is_active,created_at) VALUES (?,?,?,?,1,datetime('now','localtime'))",
                          (u, pw_hash, salt, r))

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

def get_incidents(type=None, camera=None, from_date=None, to_date=None, status=None, page=1, limit=50):
    query = "SELECT id, camera_id, type, confidence, snapshot, created_at, status, resolved_at, resolved_by FROM violations WHERE 1=1"
    params = []
    
    if type:
        query += " AND type = ?"
        params.append(type)
    if camera:
        query += " AND camera_id = ?"
        params.append(camera)
    if from_date:
        query += " AND created_at >= ?"
        params.append(from_date)
    if to_date:
        query += " AND created_at <= ?"
        params.append(to_date)
    if status:
        query += " AND status = ?"
        params.append(status)
        
    count_query = query.replace("SELECT id, camera_id, type, confidence, snapshot, created_at, status, resolved_at, resolved_by", "SELECT COUNT(*)")
    
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    offset = (page - 1) * limit
    params.extend([limit, offset])
    
    with _conn() as c:
        c.row_factory = sqlite3.Row
        total = c.execute(count_query, params[:-2]).fetchone()[0]
        rows = c.execute(query, params).fetchall()
        
    return {
        "incidents": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if total > 0 else 1
    }

def resolve_incident(vid: int, resolved_by: str):
    with _conn() as c:
        c.execute(
            "UPDATE violations SET status = 'resolved', resolved_at = datetime('now','localtime'), resolved_by = ? WHERE id = ?",
            (resolved_by, vid)
        )
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM violations WHERE id = ?", (vid,)).fetchone()
        return dict(row) if row else None

def export_incidents_csv(filters: dict):
    filters['limit'] = 1000000
    filters['page'] = 1
    data = get_incidents(**filters)
    incidents = data["incidents"]
    
    output = io.StringIO()
    if not incidents:
        return ""
    writer = csv.DictWriter(output, fieldnames=incidents[0].keys())
    writer.writeheader()
    writer.writerows(incidents)
    return output.getvalue()

def list_cameras():
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM cameras ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def upsert_camera(cam_id, name, type, uri):
    with _conn() as c:
        c.execute("""
            INSERT INTO cameras (id, name, type, uri)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                uri = excluded.uri
        """, (cam_id, name, type, uri))

def update_camera_status(cam_id, status, error_msg=None):
    with _conn() as c:
        c.execute("UPDATE cameras SET status = ?, error_msg = ? WHERE id = ?", (status, error_msg, cam_id))

def delete_camera(cam_id):
    with _conn() as c:
        c.execute("DELETE FROM cameras WHERE id = ?", (cam_id,))

class DuplicateUserError(Exception):
    pass

# ---------- auth ----------
def verify_login(username, password):
    locked, remaining = is_account_locked(username)
    if locked:
        return {"error": "locked", "retry_after": remaining}

    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT id, username, password_hash, salt, role, is_active FROM users WHERE username=?",
                        (username,)).fetchone()
    if not row:
        record_login_failure(username)
        return None

    if not row["is_active"]:
        return {"error": "disabled"}

    valid, needs_upgrade = verify_pw(password, row["password_hash"], row["salt"])
    if not valid:
        record_login_failure(username)
        return None

    record_login_success(username)
    if needs_upgrade:
        upgrade_pw(username, password)

    token = secrets.token_hex(24)
    with _conn() as c:
        c.execute("INSERT INTO tokens (token, username, role) VALUES (?,?,?)",
                  (token, username, row["role"]))
    return {"token": token, "username": username, "role": row["role"]}

def check_token(token):
    if not token:
        return None
    ttl_hours = getattr(config, "TOKEN_TTL_HOURS", 12)
    with _conn() as c:
        # Opportunistic purge of expired tokens
        try:
            c.execute(
                "DELETE FROM tokens WHERE datetime(created_at, '+' || ? || ' hours') < datetime('now','localtime')",
                (ttl_hours,)
            )
        except sqlite3.OperationalError:
            pass

        c.row_factory = sqlite3.Row
        row = c.execute("""
            SELECT t.token, t.username, t.role, t.created_at, u.is_active
            FROM tokens t
            JOIN users u ON t.username = u.username
            WHERE t.token = ?
        """, (token,)).fetchone()

        if not row:
            return None

        if not row["is_active"]:
            c.execute("DELETE FROM tokens WHERE username = ?", (row["username"],))
            return None

        # Enforce TTL for this token
        is_valid = c.execute(
            "SELECT 1 FROM tokens WHERE token = ? AND datetime(created_at, '+' || ? || ' hours') >= datetime('now','localtime')",
            (token, ttl_hours)
        ).fetchone()
        if not is_valid:
            c.execute("DELETE FROM tokens WHERE token = ?", (token,))
            return None

        return {"username": row["username"], "role": row["role"]}

def revoke_token(token: str) -> bool:
    if not token:
        return False
    with _conn() as c:
        cur = c.execute("DELETE FROM tokens WHERE token = ?", (token,))
        return cur.rowcount > 0

def revoke_user_sessions(username: str) -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM tokens WHERE username = ?", (username,))
        return cur.rowcount

def register_user(username: str, password: str, email: str = None) -> dict:
    username = username.strip() if username else ""
    if not username:
        raise ValueError("Username cannot be empty")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    salt = secrets.token_hex(16)
    pw_hash = hash_pw_pbkdf2(password, salt)

    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO users (username, password_hash, salt, role, email, is_active, created_at) "
                "VALUES (?,?,?,?,?,1,datetime('now','localtime'))",
                (username, pw_hash, salt, "viewer", email)
            )
        except sqlite3.IntegrityError:
            raise DuplicateUserError(f"Username '{username}' already exists")

    return {"username": username, "role": "viewer", "email": email, "is_active": 1}

def list_users() -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT id, username, email, role, is_active, COALESCE(created_at, '') AS created_at FROM users ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]

def set_user_role(user_id: int, new_role: str) -> dict:
    if new_role not in ("admin", "viewer"):
        raise ValueError(f"Invalid role: {new_role}")

    with _conn() as c:
        c.row_factory = sqlite3.Row
        user = c.execute("SELECT id, username, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return None

        # Cannot demote the last active admin
        if user["role"] == "admin" and new_role != "admin" and user["is_active"] == 1:
            admin_count = c.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
                (user_id,)
            ).fetchone()[0]
            if admin_count == 0:
                raise ValueError("Cannot demote the last active administrator")

        c.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        c.execute("UPDATE tokens SET role = ? WHERE username = ?", (new_role, user["username"]))
        return {"id": user_id, "username": user["username"], "role": new_role}

def toggle_user_active(user_id: int, current_admin_username: str) -> dict:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        user = c.execute("SELECT id, username, role, is_active FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return None

        # Cannot disable self
        if user["username"] == current_admin_username:
            raise ValueError("Cannot disable your own account")

        # Cannot disable last active admin
        if user["role"] == "admin" and user["is_active"] == 1:
            admin_count = c.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
                (user_id,)
            ).fetchone()[0]
            if admin_count == 0:
                raise ValueError("Cannot disable the last active administrator")

        new_status = 0 if user["is_active"] else 1
        c.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))

        if new_status == 0:
            c.execute("DELETE FROM tokens WHERE username = ?", (user["username"],))

        return {"id": user_id, "username": user["username"], "is_active": new_status}