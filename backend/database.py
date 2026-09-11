import sqlite3, hashlib, secrets, csv, io, hmac, time, json
from datetime import datetime, timedelta
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
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT NOT NULL,
            name TEXT NOT NULL,
            points TEXT NOT NULL,
            requirement TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_violations_created_at ON violations(created_at);
        CREATE INDEX IF NOT EXISTS idx_violations_cam_type ON violations(camera_id, type);
        CREATE INDEX IF NOT EXISTS idx_zones_camera ON zones(camera_id);
        """)

        # Robust migration for zones table
        z_cols = {row[1] for row in c.execute("PRAGMA table_info(zones)").fetchall()}
        if z_cols:
            if "enabled" not in z_cols:
                c.execute("ALTER TABLE zones ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
            if "created_at" not in z_cols:
                c.execute("ALTER TABLE zones ADD COLUMN created_at TEXT")
                c.execute("UPDATE zones SET created_at = datetime('now','localtime') WHERE created_at IS NULL OR created_at = ''")

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
        c.execute("DELETE FROM zones WHERE camera_id = ?", (cam_id,))

# ---------- zones ----------
def create_zone(camera_id: str, name: str, points: list | str, requirement: str) -> dict:
    if isinstance(points, list):
        points_str = json.dumps(points)
        points_list = points
    else:
        points_str = points
        try:
            points_list = json.loads(points)
        except Exception:
            points_list = []

    with _conn() as c:
        cur = c.execute(
            """INSERT INTO zones (camera_id, name, points, requirement, enabled, created_at)
               VALUES (?, ?, ?, ?, 1, datetime('now','localtime'))""",
            (camera_id, name, points_str, requirement)
        )
        zone_id = cur.lastrowid
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM zones WHERE id = ?", (zone_id,)).fetchone()
        res = dict(row)
        res["points"] = points_list
        return res

def get_zones(camera_id: str = None, enabled_only: bool = False) -> list[dict]:
    query = "SELECT id, camera_id, name, points, requirement, enabled, created_at FROM zones WHERE 1=1"
    params = []
    if camera_id:
        query += " AND camera_id = ?"
        params.append(camera_id)
    if enabled_only:
        query += " AND enabled = 1"
    query += " ORDER BY created_at ASC, id ASC"

    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["points"] = json.loads(d["points"])
            except Exception:
                d["points"] = []
            result.append(d)
        return result

def get_zone_by_id(zone_id: int) -> dict | None:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT id, camera_id, name, points, requirement, enabled, created_at FROM zones WHERE id = ?", (zone_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["points"] = json.loads(d["points"])
        except Exception:
            d["points"] = []
        return d

def get_zone(zone_id: int) -> dict | None:
    return get_zone_by_id(zone_id)

def toggle_zone(zone_id: int) -> dict | None:
    with _conn() as c:
        cur = c.execute("UPDATE zones SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END WHERE id = ?", (zone_id,))
        if cur.rowcount == 0:
            return None
    return get_zone_by_id(zone_id)

def delete_zone_by_id(zone_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        return cur.rowcount > 0

def delete_zone(zone_id: int) -> bool:
    return delete_zone_by_id(zone_id)

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


# ---------- analytics & reports aggregates ----------
def _parse_date_range(from_date=None, to_date=None, default_days=7):
    now = datetime.now()
    if not to_date:
        to_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        to_str = str(to_date).strip().replace("T", " ")
        if len(to_str) == 10:
            to_str += " 23:59:59"
        to_dt = datetime.strptime(to_str[:19], "%Y-%m-%d %H:%M:%S")

    if not from_date:
        from_dt = (now - timedelta(days=default_days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        from_str = str(from_date).strip().replace("T", " ")
        if len(from_str) == 10:
            from_str += " 00:00:00"
        from_dt = datetime.strptime(from_str[:19], "%Y-%m-%d %H:%M:%S")

    if from_dt > to_dt:
        from_dt, to_dt = to_dt, from_dt

    from_str_out = from_dt.strftime("%Y-%m-%d %H:%M:%S")
    to_str_out = to_dt.strftime("%Y-%m-%d %H:%M:%S")
    return from_dt, to_dt, from_str_out, to_str_out


def get_analytics_summary(from_date=None, to_date=None) -> dict:
    from_dt, to_dt, from_str_out, to_str_out = _parse_date_range(from_date, to_date, default_days=7)

    # Calculate total hours in range
    if to_dt.hour == 23 and to_dt.minute == 59 and to_dt.second == 59 and from_dt.hour == 0 and from_dt.minute == 0 and from_dt.second == 0:
        total_hours = float(((to_dt.date() - from_dt.date()).days + 1) * 24)
    else:
        total_seconds = (to_dt - from_dt).total_seconds()
        total_hours = max(1.0, round(total_seconds / 3600.0, 2))

    with _conn() as c:
        # 1. Total and resolved counts
        row = c.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
        """, (from_str_out, to_str_out)).fetchone()

        total = row[0] or 0
        resolved = row[1] or 0
        open_cnt = total - resolved
        resolution_rate = round((resolved / total) * 100.0, 1) if total > 0 else 100.0

        # 2. Distinct violation hours (dirty hours)
        violation_hours_count = c.execute("""
            SELECT COUNT(DISTINCT strftime('%Y-%m-%d %H', created_at))
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
        """, (from_str_out, to_str_out)).fetchone()[0] or 0

        dirty_hours = violation_hours_count
        violations_per_dirty_hour = round(total / dirty_hours, 1) if dirty_hours > 0 else 0

        if total == 0:
            clean_hours = total_hours
            compliance_score = 100.0
        else:
            clean_hours = max(0.0, round(total_hours - violation_hours_count, 2))
            compliance_score = round((clean_hours / total_hours) * 100.0, 1)

        # 3. Busiest camera and per-camera distribution
        cam_rows = c.execute("""
            SELECT camera_id, COUNT(*) AS cnt
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY camera_id
            ORDER BY cnt DESC
        """, (from_str_out, to_str_out)).fetchall()

        if cam_rows:
            busiest_camera = {"camera_id": cam_rows[0][0], "count": cam_rows[0][1]}
        else:
            busiest_camera = {"camera_id": "NONE", "count": 0}

        by_camera = [{"camera_id": r[0], "count": r[1]} for r in cam_rows]

        # 4. By type breakdown
        type_rows = c.execute("""
            SELECT type, COUNT(*) AS cnt
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY type
            ORDER BY cnt DESC
        """, (from_str_out, to_str_out)).fetchall()

        by_type = [{"type": r[0], "count": r[1]} for r in type_rows]

        # 5. Daily trend (zero-filled across entire calendar range in Python)
        day_rows = c.execute("""
            SELECT strftime('%Y-%m-%d', created_at) AS day, COUNT(*) AS cnt
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY day
            ORDER BY day ASC
        """, (from_str_out, to_str_out)).fetchall()
        day_map = {r[0]: r[1] for r in day_rows}

        daily_trend = []
        curr_d = from_dt.date()
        end_d = to_dt.date()
        while curr_d <= end_d:
            d_str = curr_d.strftime("%Y-%m-%d")
            daily_trend.append({"date": d_str, "count": day_map.get(d_str, 0)})
            curr_d += timedelta(days=1)

        # 6. Hourly trend (zero-filled 00..23 in Python)
        hr_rows = c.execute("""
            SELECT strftime('%H', created_at) AS hr, COUNT(*) AS cnt
            FROM violations
            WHERE created_at >= ? AND created_at <= ?
            GROUP BY hr
        """, (from_str_out, to_str_out)).fetchall()
        hr_map = {r[0]: r[1] for r in hr_rows}

        hourly_trend = []
        for h in range(24):
            h_str = f"{h:02d}"
            hourly_trend.append({
                "hour": h_str,
                "hour_num": h,
                "count": hr_map.get(h_str, 0)
            })

    return {
        "range": {
            "from_date": from_str_out,
            "to_date": to_str_out,
            "total_hours": total_hours,
            "clean_hours": clean_hours,
            "violation_hours": violation_hours_count
        },
        "kpis": {
            "total_violations": total,
            "open_violations": open_cnt,
            "resolved_violations": resolved,
            "resolution_rate": resolution_rate,
            "compliance_score": compliance_score,
            "compliance_formula": "100 * (clean_hours / total_hours)",
            "dirty_hours": dirty_hours,
            "violations_per_dirty_hour": violations_per_dirty_hour,
            "busiest_camera": busiest_camera
        },
        "trends": {
            "daily": daily_trend,
            "hourly": hourly_trend
        },
        "breakdown": {
            "by_type": by_type,
            "by_camera": by_camera
        }
    }


def get_report_data(from_date=None, to_date=None, camera=None, type=None, limit=10, generated_by="operator") -> dict:
    from_dt, to_dt, from_str_out, to_str_out = _parse_date_range(from_date, to_date, default_days=7)

    where_clauses = ["created_at >= ?", "created_at <= ?"]
    params = [from_str_out, to_str_out]

    if camera:
        where_clauses.append("camera_id = ?")
        params.append(camera)
    if type:
        where_clauses.append("type = ?")
        params.append(type)

    where_sql = " AND ".join(where_clauses)

    if to_dt.hour == 23 and to_dt.minute == 59 and to_dt.second == 59 and from_dt.hour == 0 and from_dt.minute == 0 and from_dt.second == 0:
        total_hours = float(((to_dt.date() - from_dt.date()).days + 1) * 24)
    else:
        total_seconds = (to_dt - from_dt).total_seconds()
        total_hours = max(1.0, round(total_seconds / 3600.0, 2))

    with _conn() as c:
        c.row_factory = sqlite3.Row

        summary_row = c.execute(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved,
                SUM(CASE WHEN status = 'open' OR status IS NULL THEN 1 ELSE 0 END) as open_cnt
            FROM violations
            WHERE {where_sql}
        """, params).fetchone()

        total = summary_row["total"] or 0
        resolved = summary_row["resolved"] or 0
        open_cnt = summary_row["open_cnt"] or 0
        resolution_rate = round((resolved / total) * 100.0, 1) if total > 0 else 100.0

        violation_hours_count = c.execute(f"""
            SELECT COUNT(DISTINCT strftime('%Y-%m-%d %H', created_at))
            FROM violations
            WHERE {where_sql}
        """, params).fetchone()[0] or 0

        dirty_hours = violation_hours_count
        violations_per_dirty_hour = round(total / dirty_hours, 1) if dirty_hours > 0 else 0

        if total == 0:
            clean_hours = total_hours
            compliance_score = 100.0
        else:
            clean_hours = max(0.0, round(total_hours - violation_hours_count, 2))
            compliance_score = round((clean_hours / total_hours) * 100.0, 1)

        by_type_rows = c.execute(f"""
            SELECT type, COUNT(*) as cnt
            FROM violations
            WHERE {where_sql}
            GROUP BY type
            ORDER BY cnt DESC
        """, params).fetchall()
        by_type = [
            {
                "type": r["type"],
                "count": r["cnt"],
                "percentage": round((r["cnt"] / total) * 100.0, 1) if total > 0 else 0.0
            }
            for r in by_type_rows
        ]

        by_cam_rows = c.execute(f"""
            SELECT camera_id, COUNT(*) as cnt
            FROM violations
            WHERE {where_sql}
            GROUP BY camera_id
            ORDER BY cnt DESC
        """, params).fetchall()
        by_camera = [
            {
                "camera_id": r["camera_id"],
                "count": r["cnt"],
                "percentage": round((r["cnt"] / total) * 100.0, 1) if total > 0 else 0.0
            }
            for r in by_cam_rows
        ]

        evidence_params = list(params) + [limit]
        evidence_rows = c.execute(f"""
            SELECT id, camera_id, type, confidence, snapshot, created_at, status, resolved_by
            FROM violations
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ?
        """, evidence_params).fetchall()

        top_evidence = []
        for r in evidence_rows:
            snap = r["snapshot"]
            safe_snap = snap.replace("\\", "/").split("/")[-1] if snap else None
            snap_url = f"/snapshots/{safe_snap}" if safe_snap else None
            top_evidence.append({
                "id": r["id"],
                "camera_id": r["camera_id"],
                "type": r["type"],
                "confidence": r["confidence"],
                "snapshot": r["snapshot"],
                "snapshot_url": snap_url,
                "created_at": r["created_at"],
                "status": r["status"],
                "resolved_by": r["resolved_by"]
            })

    return {
        "metadata": {
            "site": "SafetyLens Site Ops Command",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generated_by": generated_by,
            "from_date": from_str_out,
            "to_date": to_str_out,
            "filters": {
                "camera": camera,
                "type": type
            }
        },
        "summary": {
            "total_violations": total,
            "open_violations": open_cnt,
            "resolved_violations": resolved,
            "resolution_rate": resolution_rate,
            "compliance_score": compliance_score,
            "total_hours": total_hours,
            "dirty_hours": dirty_hours,
            "violations_per_dirty_hour": violations_per_dirty_hour
        },
        "by_type": by_type,
        "by_camera": by_camera,
        "top_evidence": top_evidence
    }


def export_report_csv(filters: dict) -> str:
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    camera = filters.get("camera")
    vtype = filters.get("type")

    from_dt, to_dt, from_str_out, to_str_out = _parse_date_range(from_date, to_date, default_days=7)

    where_clauses = ["created_at >= ?", "created_at <= ?"]
    params = [from_str_out, to_str_out]

    if camera:
        where_clauses.append("camera_id = ?")
        params.append(camera)
    if vtype:
        where_clauses.append("type = ?")
        params.append(vtype)

    where_sql = " AND ".join(where_clauses)

    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(f"""
            SELECT id, camera_id, type, confidence, snapshot, created_at, status, resolved_at, resolved_by
            FROM violations
            WHERE {where_sql}
            ORDER BY created_at DESC
        """, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "camera_id", "type", "confidence", "snapshot", "created_at", "status", "resolved_at", "resolved_by"])
    for r in rows:
        writer.writerow([
            r["id"],
            r["camera_id"],
            r["type"],
            r["confidence"],
            r["snapshot"],
            r["created_at"],
            r["status"],
            r["resolved_at"] or "",
            r["resolved_by"] or ""
        ])
    return output.getvalue()