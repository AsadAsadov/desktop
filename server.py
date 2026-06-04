import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:  # pragma: no cover - requirements.txt includes Flask-Limiter
    Limiter = None
    get_remote_address = None

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "screens")).resolve()
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "monitor.db")).resolve()
KEEP_MINUTES = int(os.environ.get("SCREENSHOT_KEEP_MINUTES", "5"))
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "8")) * 1024 * 1024
ONLINE_SECONDS = int(os.environ.get("ONLINE_SECONDS", "15"))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "consent_monitor_session")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "webp", "png"}
CLIENT_VERSION_HEADER = "X-Client-Version"
LAST_CLEANUP = 0.0

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48),
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
    PREFERRED_URL_SCHEME="https" if SESSION_COOKIE_SECURE else "http",
)

if not os.environ.get("SECRET_KEY"):
    app.logger.warning("SECRET_KEY is not set. Generate a strong value for production.")
if not ADMIN_EMAIL:
    app.logger.warning("ADMIN_EMAIL is not set. Login is disabled until configured.")
if not ADMIN_PASSWORD_HASH and ADMIN_PASSWORD:
    app.logger.warning("ADMIN_PASSWORD is supported for setup only. Prefer ADMIN_PASSWORD_HASH.")
if not ADMIN_PASSWORD_HASH and not ADMIN_PASSWORD:
    app.logger.warning("ADMIN_PASSWORD_HASH is not set. Login is disabled until configured.")

limiter = Limiter(get_remote_address, app=app, default_limits=["300 per minute"]) if Limiter else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_now() -> str:
    return utcnow().isoformat()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def normalize_name(value: str, fallback: str = "UNKNOWN") -> str:
    cleaned = secure_filename((value or fallback).strip())[:80]
    return cleaned or fallback


def validate_filename(filename: str) -> str:
    safe = secure_filename(filename)
    if not safe or safe != filename or "/" in safe or "\\" in safe:
        abort(400, "Yanlış fayl adı")
    return safe


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'enrolled',
                last_seen TEXT,
                os TEXT,
                username TEXT,
                active_window TEXT,
                active_process TEXT,
                client_version TEXT,
                paused_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER UNIQUE,
                agent_name TEXT UNIQUE,
                full_name TEXT,
                email TEXT,
                department TEXT,
                role TEXT,
                phone TEXT,
                note TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT,
                action TEXT NOT NULL,
                agent_id INTEGER,
                ip TEXT,
                user_agent TEXT,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_screenshots_agent_time ON screenshots(agent_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
            """
        )
        # Add columns when upgrading from the older single-file prototype.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        for column, ddl in {
            "token_hash": "ALTER TABLE agents ADD COLUMN token_hash TEXT",
            "status": "ALTER TABLE agents ADD COLUMN status TEXT NOT NULL DEFAULT 'enrolled'",
            "os": "ALTER TABLE agents ADD COLUMN os TEXT",
            "username": "ALTER TABLE agents ADD COLUMN username TEXT",
            "client_version": "ALTER TABLE agents ADD COLUMN client_version TEXT",
            "paused_at": "ALTER TABLE agents ADD COLUMN paused_at TEXT",
            "created_at": "ALTER TABLE agents ADD COLUMN created_at TEXT",
        }.items():
            if column not in existing:
                conn.execute(ddl)
        existing_shots = {row[1] for row in conn.execute("PRAGMA table_info(screenshots)").fetchall()}
        if "agent_id" not in existing_shots:
            conn.execute("ALTER TABLE screenshots ADD COLUMN agent_id INTEGER")
        existing_emp = {row[1] for row in conn.execute("PRAGMA table_info(employees)").fetchall()}
        for column, ddl in {
            "agent_id": "ALTER TABLE employees ADD COLUMN agent_id INTEGER",
            "email": "ALTER TABLE employees ADD COLUMN email TEXT",
            "phone": "ALTER TABLE employees ADD COLUMN phone TEXT",
            "created_at": "ALTER TABLE employees ADD COLUMN created_at TEXT",
            "updated_at": "ALTER TABLE employees ADD COLUMN updated_at TEXT",
        }.items():
            if column not in existing_emp:
                conn.execute(ddl)


def audit(action: str, actor: Optional[str] = None, agent_id: Optional[int] = None, details: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (actor, action, agent_id, ip, user_agent, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor or session.get("email") or "system",
                action,
                agent_id,
                request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip() if request else "",
                request.headers.get("User-Agent", "")[:240] if request else "",
                details[:500],
                iso_now(),
            ),
        )


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_csrf() -> None:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint != "upload":
        form_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not form_token or not hmac.compare_digest(form_token, session.get("csrf_token", "")):
            abort(400, "CSRF token yanlışdır")


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store" if request.endpoint and request.endpoint.startswith("api_") else "no-cache")
    if SESSION_COOKIE_SECURE:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.full_path))
        return fn(*args, **kwargs)

    return wrapper


def password_ok(password: str) -> bool:
    if not ADMIN_EMAIL:
        return False
    if ADMIN_PASSWORD_HASH:
        return check_password_hash(ADMIN_PASSWORD_HASH, password)
    return bool(ADMIN_PASSWORD) and hmac.compare_digest(ADMIN_PASSWORD, password)


def load_agents():
    threshold = utcnow() - timedelta(seconds=ONLINE_SECONDS)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT a.*, e.full_name, e.email, e.department, e.role, e.phone, e.note
            FROM agents a
            LEFT JOIN employees e ON e.agent_id = a.id OR (e.agent_id IS NULL AND e.agent_name = a.name)
            ORDER BY COALESCE(e.department, 'Digər'), a.name
            """
        ).fetchall()
    agents = []
    for row in rows:
        last_seen = parse_dt(row["last_seen"])
        online = bool(last_seen and last_seen >= threshold and row["status"] != "paused")
        item = dict(row)
        item["online"] = online
        item["last_seen_display"] = last_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if last_seen else "Heç vaxt"
        item["status_label"] = "Pauzada" if row["status"] == "paused" else ("Online" if online else "Offline")
        agents.append(item)
    return agents


def authenticate_agent():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        abort(401, "Bearer token tələb olunur")
    incoming_hash = token_hash(auth.removeprefix("Bearer ").strip())
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE token_hash = ?", (incoming_hash,)).fetchone()
    if not agent:
        abort(401, "Token yanlışdır")
    return agent


def cleanup_old_screenshots() -> None:
    cutoff = utcnow() - timedelta(minutes=KEEP_MINUTES)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename FROM screenshots WHERE created_at < ?", (cutoff.isoformat(),)
        ).fetchall()
        for row in rows:
            filename = row["filename"]
            if filename.endswith("_last.jpg"):
                continue
            try:
                (UPLOAD_FOLDER / validate_filename(filename)).unlink(missing_ok=True)
            except Exception as exc:
                app.logger.warning("Screenshot cleanup failed for %s: %s", filename, exc)
            conn.execute("DELETE FROM screenshots WHERE id = ?", (row["id"],))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"]) if limiter else (lambda f: f)
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if email == ADMIN_EMAIL.lower() and password_ok(password):
            session.clear()
            session["logged_in"] = True
            session["email"] = email
            csrf_token()
            audit("login", actor=email)
            return redirect(request.args.get("next") or url_for("dashboard"))
        audit("login_failed", actor=email or "anonymous", details="Invalid credentials")
        flash("Email və ya şifrə yanlışdır.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    email = session.get("email")
    audit("logout", actor=email)
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["POST"])
def upload():
    global LAST_CLEANUP
    agent = authenticate_agent()
    file = request.files.get("screenshot")

    now = utcnow()
    pc_name = normalize_name(request.form.get("pc_name") or agent["name"])
    status = request.form.get("status", "online")
    active_window = request.form.get("active_window", "")[:500]
    active_process = request.form.get("active_process", "")[:180]
    os_version = request.form.get("os", "")[:180]
    username = request.form.get("username", "")[:180]
    client_version = request.form.get("client_version") or request.headers.get(CLIENT_VERSION_HEADER, "")[:80]

    filename = None
    if status != "paused":
        if not file or not file.filename:
            abort(400, "Screenshot tələb olunur")
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
        if ext not in ALLOWED_EXTENSIONS:
            abort(400, "Dəstəklənməyən şəkil formatı")
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        filename = f"agent_{agent['id']}_{timestamp}.{ext}"
        latest_filename = f"agent_{agent['id']}_last.jpg"
        file_path = UPLOAD_FOLDER / filename
        latest_path = UPLOAD_FOLDER / latest_filename
        file.save(file_path)
        try:
            file.stream.seek(0)
            file.save(latest_path)
        except Exception:
            latest_path.write_bytes(file_path.read_bytes())

    with get_db() as conn:
        conn.execute(
            """
            UPDATE agents
            SET name = ?, status = ?, last_seen = ?, os = ?, username = ?, active_window = ?,
                active_process = ?, client_version = ?, paused_at = CASE WHEN ? = 'paused' THEN ? ELSE NULL END
            WHERE id = ?
            """,
            (pc_name, "paused" if status == "paused" else "online", now.isoformat(), os_version, username,
             active_window, active_process, client_version, status, now.isoformat(), agent["id"]),
        )
        if filename:
            conn.execute(
                "INSERT INTO screenshots (agent_id, filename, created_at) VALUES (?, ?, ?)",
                (agent["id"], filename, now.isoformat()),
            )

    if status == "paused":
        audit("pause", actor=pc_name, agent_id=agent["id"], details="Client reported paused state")

    if time.time() - LAST_CLEANUP > 60:
        cleanup_old_screenshots()
        LAST_CLEANUP = time.time()
    return jsonify({"ok": True})


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", agents=load_agents(), keep_minutes=KEEP_MINUTES)


@app.route("/enroll", methods=["GET", "POST"])
@login_required
def enroll():
    generated_token = None
    if request.method == "POST":
        name = normalize_name(request.form.get("name"), "NEW_DEVICE")
        raw_token = secrets.token_urlsafe(32)
        created = iso_now()
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO agents (name, token_hash, status, created_at) VALUES (?, ?, 'enrolled', ?)",
                (name, token_hash(raw_token), created),
            )
            agent_id = cur.lastrowid
        audit("device_enrollment", agent_id=agent_id, details=f"Device {name} enrolled")
        generated_token = raw_token
        flash("Token yaradıldı. Bu token yalnız indi göstərilir.", "success")
    return render_template("enroll.html", generated_token=generated_token)


@app.route("/employees", methods=["GET", "POST"])
@login_required
def employees():
    with get_db() as conn:
        agents = conn.execute("SELECT id, name FROM agents ORDER BY name").fetchall()
        if request.method == "POST":
            agent_id = int(request.form.get("agent_id", "0") or 0) or None
            agent_name = normalize_name(request.form.get("agent_name") or "") if not agent_id else None
            now = iso_now()
            conn.execute(
                """
                INSERT INTO employees (agent_id, agent_name, full_name, email, department, role, phone, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    full_name=excluded.full_name, email=excluded.email, department=excluded.department,
                    role=excluded.role, phone=excluded.phone, note=excluded.note, updated_at=excluded.updated_at
                """,
                (
                    agent_id,
                    agent_name,
                    request.form.get("full_name", "")[:180],
                    request.form.get("email", "")[:180],
                    request.form.get("department", "")[:120],
                    request.form.get("role", "")[:120],
                    request.form.get("phone", "")[:80],
                    request.form.get("note", "")[:500],
                    now,
                    now,
                ),
            )
            audit("employee_update", details="Employee metadata changed")
            return redirect(url_for("employees"))
        rows = conn.execute(
            """
            SELECT e.*, a.name AS linked_agent_name
            FROM employees e LEFT JOIN agents a ON a.id = e.agent_id
            ORDER BY COALESCE(e.department, ''), COALESCE(e.full_name, e.agent_name, a.name)
            """
        ).fetchall()
    return render_template("employees.html", employees=rows, agents=agents)


@app.route("/agent/<int:agent_id>")
@login_required
def agent_detail(agent_id: int):
    with get_db() as conn:
        agent = conn.execute(
            """
            SELECT a.*, e.full_name, e.department, e.role, e.note
            FROM agents a LEFT JOIN employees e ON e.agent_id = a.id OR (e.agent_id IS NULL AND e.agent_name = a.name)
            WHERE a.id = ?
            """,
            (agent_id,),
        ).fetchone()
    if not agent:
        abort(404)
    audit("screen_view", agent_id=agent_id, details="Detail viewer opened")
    return render_template("detail.html", agent=dict(agent))


@app.route("/agent/<int:agent_id>/gallery")
@login_required
def gallery(agent_id: int):
    with get_db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not agent:
        abort(404)
    return render_template("gallery.html", agent=dict(agent), keep_minutes=KEEP_MINUTES)


@app.route("/screens/<path:filename>")
@login_required
def screens(filename: str):
    return send_from_directory(UPLOAD_FOLDER, validate_filename(filename), max_age=0)


@app.route("/api/agents")
@login_required
def api_agents():
    return jsonify({"agents": load_agents(), "server_time": iso_now()})


@app.route("/api/agent/<int:agent_id>/last")
@login_required
def api_agent_last(agent_id: int):
    with get_db() as conn:
        agent = conn.execute("SELECT id, last_seen, active_window, active_process, status FROM agents WHERE id = ?", (agent_id,)).fetchone()
        shot = conn.execute(
            "SELECT filename, created_at FROM screenshots WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
    if not agent or not shot:
        return jsonify({"ok": False}), 404
    return jsonify(
        {
            "ok": True,
            "filename": shot["filename"],
            "latest_url": url_for("screens", filename=shot["filename"]),
            "created_at": shot["created_at"],
            "last_seen": agent["last_seen"],
            "active_window": agent["active_window"],
            "active_process": agent["active_process"],
            "status": agent["status"],
        }
    )


@app.route("/api/agent/<int:agent_id>/shots")
@login_required
def api_agent_shots(agent_id: int):
    since = utcnow() - timedelta(minutes=KEEP_MINUTES)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT filename, created_at FROM screenshots
            WHERE agent_id = ? AND created_at >= ?
            ORDER BY created_at DESC LIMIT 300
            """,
            (agent_id, since.isoformat()),
        ).fetchall()
    return jsonify([
        {"filename": row["filename"], "created_at": row["created_at"], "url": url_for("screens", filename=row["filename"])}
        for row in rows
    ])


@app.route("/api/events")
@login_required
def api_events():
    def stream():
        while True:
            payload = json.dumps({"agents": load_agents(), "server_time": iso_now()}, default=str)
            yield f"event: agents\ndata: {payload}\n\n"
            time.sleep(2)
    return Response(stream(), mimetype="text/event-stream")


@app.route("/api/agent/<int:agent_id>/video", methods=["POST"])
@login_required
def create_video(agent_id: int):
    try:
        import cv2  # type: ignore
    except ImportError:
        return jsonify({"ok": False, "error": "Video yaratmaq üçün opencv-python-headless paketini quraşdırın."}), 503

    since = utcnow() - timedelta(minutes=KEEP_MINUTES)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT filename FROM screenshots WHERE agent_id = ? AND created_at >= ? ORDER BY created_at ASC",
            (agent_id, since.isoformat()),
        ).fetchall()
    if len(rows) < 2:
        return jsonify({"ok": False, "error": "Video üçün kifayət qədər görüntü yoxdur."}), 400

    first = cv2.imread(str(UPLOAD_FOLDER / validate_filename(rows[0]["filename"])))
    if first is None:
        return jsonify({"ok": False, "error": "Görüntüləri oxumaq mümkün olmadı."}), 500
    height, width = first.shape[:2]
    output_name = f"agent_{agent_id}_last_{int(time.time())}.mp4"
    output_path = UPLOAD_FOLDER / output_name
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), 2, (width, height))
    for row in rows:
        frame = cv2.imread(str(UPLOAD_FOLDER / validate_filename(row["filename"])))
        if frame is None:
            continue
        if frame.shape[:2] != (height, width):
            frame = cv2.resize(frame, (width, height))
        writer.write(frame)
    writer.release()
    audit("video_create", agent_id=agent_id, details="Created last five minutes video")
    return jsonify({"ok": True, "url": url_for("screens", filename=output_name)})


@app.route("/audit")
@login_required
def audit_page():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT l.*, a.name AS agent_name
            FROM audit_logs l LEFT JOIN agents a ON a.id = l.agent_id
            ORDER BY l.created_at DESC LIMIT 300
            """
        ).fetchall()
    return render_template("audit.html", logs=rows)


init_db()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
