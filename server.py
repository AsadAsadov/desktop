import os
import time
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    request,
    send_from_directory,
    render_template_string,
    redirect,
    url_for,
    session,
    jsonify,
)


# ==============================
#   SERVER SCREEN TƏMİZLƏMƏ (son 10 dəqiqə)
# ==============================

SCREEN_FOLDER = "screens"
KEEP_MINUTES = 10  # yalnız son 10 dəqiqə qalacaq


def cleanup_server_screens():
    base = SCREEN_FOLDER
    if not os.path.exists(base):
        return

    now = datetime.utcnow()
    limit = now - timedelta(minutes=KEEP_MINUTES)

    for filename in os.listdir(base):
        file_path = os.path.join(base, filename)

        # yalnız faylları təmizlə (qovluqlara toxunma)
        if not os.path.isfile(file_path):
            continue

        try:
            # həm create time, həm modify time nəzərə alınır
            created_at = datetime.utcfromtimestamp(os.path.getctime(file_path))
            modified_at = datetime.utcfromtimestamp(os.path.getmtime(file_path))

            file_time = min(created_at, modified_at)

            if file_time < limit:
                os.remove(file_path)
                print(f"[SERVER CLEAN] Silindi → {file_path}")

        except Exception as e:
            print(f"[SERVER CLEAN ERROR] {file_path} → {e}")


# ==============================
#   KONFİQURASİYA
# ==============================

UPLOAD_FOLDER = "screens"
DB_PATH = "monitor.db"

ADMIN_EMAIL = "adminbesthome@gmail.com"
ADMIN_PASSWORD = "AA161235aa"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "besthome_monitor_secret_123"
LAST_CLEANUP = 0


# ==============================
#   DB FUNKSİYALARI
# ==============================


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Agent cədvəli
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            last_seen TEXT,
            active_window TEXT,
            active_process TEXT,
            process_list TEXT
        )
        """
    )

    # Screenshot cədvəli
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT,
            filename TEXT,
            created_at TEXT
        )
        """
    )

    # İşçi cədvəli
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE,
            full_name TEXT,
            department TEXT,
            role TEXT,
            note TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ==============================
#   LOGIN DECORATOR
# ==============================


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


# ==============================
#   LOGIN / LOGOUT
# ==============================


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            session["email"] = email
            return redirect(url_for("dashboard"))
        else:
            error = "Email və ya şifrə yanlışdır."

    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>BestHome Monitor - Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <style>
            * { box-sizing: border-box; }

            body {
                background: #050910;
                color: #f0f0f0;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                padding: 16px;
            }

            .card {
                background: #0f172a;
                padding: 24px;
                border-radius: 12px;
                width: 100%;
                max-width: 360px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            }

            h1 {
                font-size: 20px;
                margin-bottom: 4px;
                line-height: 1.2;
            }

            p {
                margin-top: 0;
                color: #9ca3af;
                font-size: 13px;
            }

            label {
                font-size: 13px;
                color: #9ca3af;
                display: block;
                margin-bottom: 4px;
            }

            input {
                width: 100%;
                padding: 12px;
                border-radius: 8px;
                border: 1px solid #1f2937;
                background: #020617;
                color: #e5e7eb;
                font-size: 15px;
                margin-bottom: 14px;
                outline: none;
            }

            input:focus {
                border-color: #22c55e;
                box-shadow: 0 0 0 1px rgba(34,197,94,0.4);
            }

            button {
                width: 100%;
                padding: 12px;
                border-radius: 8px;
                border: none;
                background: #22c55e;
                color: #020617;
                font-weight: 600;
                font-size: 15px;
                cursor: pointer;
            }

            button:hover {
                background: #16a34a;
            }

            .error {
                background: rgba(239,68,68,0.1);
                border: 1px solid rgba(239,68,68,0.3);
                color: #fecaca;
                padding: 10px;
                border-radius: 8px;
                font-size: 13px;
                margin-bottom: 12px;
            }

            .logo {
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 18px;
            }

            .logo-badge {
                width: 32px;
                height: 32px;
                border-radius: 999px;
                background: radial-gradient(circle at 30% 0%, #bbf7d0, #22c55e);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 16px;
                color: #022c22;
                font-weight: 700;
            }

        </style>
    </head>

    <body>
        <div class="card">
            <div class="logo">
                <div class="logo-badge">BH</div>
                <div>
                    <h1>BestHome Monitor</h1>
                    <p>Admin giriş paneli</p>
                </div>
            </div>

            {% if error %}
            <div class="error">{{ error }}</div>
            {% endif %}

            <form method="post">
                <label>Email</label>
                <input type="email" name="email" value="{{ request.form.email or '' }}" required>

                <label>Şifrə</label>
                <input type="password" name="password" required>

                <button type="submit">Giriş</button>
            </form>
        </div>
    </body>
    </html>
    """

    return render_template_string(html, error=error)


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==============================
#   AGENT UPLOAD (SCREENSHOT + PROCESS INFO)
# ==============================


@app.route("/upload", methods=["POST"])
def upload():
    global LAST_CLEANUP

    pc_name = request.form.get("pc_name", "UNKNOWN")
    active_window = request.form.get("active_window", "")
    active_process = request.form.get("active_process", "")
    process_list = request.form.get("process_list", "")
    file = request.files.get("screenshot")

    if not file:
        return "No file", 400

    now = datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    # FULL LOG üçün fayl
    filename = f"{pc_name}_{timestamp}.jpg"
    full_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(full_path)

    # CANLI SON ŞƏKİL (dashboard üçün)
    last_image = os.path.join(UPLOAD_FOLDER, f"{pc_name}_last.jpg")
    try:
        file.stream.seek(0)
    except:
        pass
    file.save(last_image)

    # ==== SQL ƏMƏLİYYATLARI ====
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO agents (name, last_seen, active_window, active_process, process_list)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            last_seen=excluded.last_seen,
            active_window=excluded.active_window,
            active_process=excluded.active_process,
            process_list=excluded.process_list
        """,
        (pc_name, now.isoformat(), active_window, active_process, process_list),
    )

    cur.execute(
        """
        INSERT INTO screenshots (agent_name, filename, created_at)
        VALUES (?, ?, ?)
        """,
        (pc_name, filename, now.isoformat()),
    )

    conn.commit()
    conn.close()

    # === SERVER TƏMİZLƏMƏ  (10 dəqiqədən bir) ===
    now_ts = time.time()
    if now_ts - LAST_CLEANUP >= 600:  # 600s = 10 dəqiqə
        cleanup_server_screens()
        LAST_CLEANUP = now_ts

    return "OK", 200


# ==============================
#   ŞƏKİL SERVİSİ
# ==============================


@app.route("/screens/<path:filename>")
@login_required
def screens(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ==============================
#   API – SON SCREENSHOT
# ==============================


@app.route("/api/agent/<agent_name>/last")
@login_required
def api_agent_last(agent_name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT filename, created_at
        FROM screenshots
        WHERE agent_name = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (agent_name,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"ok": False}), 404

    return jsonify(
        {
            "ok": True,
            "filename": row["filename"],
            "created_at": row["created_at"],
        }
    )


# ==============================
#   API – SON 1 SAAT STATISTIKA
# ==============================


@app.route("/api/agent/<agent_name>/stats1h")
@login_required
def api_agent_stats1h(agent_name):
    now = datetime.utcnow()
    since = now - timedelta(hours=1)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at
        FROM screenshots
        WHERE agent_name = ?
          AND created_at >= ?
        """,
        (agent_name, since.isoformat()),
    )
    rows = cur.fetchall()
    conn.close()

    buckets = {}
    for r in rows:
        dt = datetime.fromisoformat(r["created_at"])
        key = dt.strftime("%H:%M")
        buckets[key] = buckets.get(key, 0) + 1

    labels = sorted(buckets.keys())
    data = [buckets[k] for k in labels]

    return jsonify({"labels": labels, "data": data})


# ==============================
#   API – 1 SAATLİK ŞƏKİL QALEREYASI (LAZY LOAD)
# ==============================


@app.route("/api/agent/<agent_name>/shots")
@login_required
def api_agent_shots(agent_name):
    offset = int(request.args.get("offset", 0))
    limit = int(request.args.get("limit", 60))

    now = datetime.utcnow()
    since = now - timedelta(hours=1)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT filename, created_at
        FROM screenshots
        WHERE agent_name = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (agent_name, since.isoformat(), limit, offset),
    )
    rows = cur.fetchall()
    conn.close()

    items = []
    for r in rows:
        dt = datetime.fromisoformat(r["created_at"])
        items.append(
            {
                "filename": r["filename"],
                "created_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return jsonify(items)


# ==============================
#   DASHBOARD
# ==============================


@app.route("/")
@login_required
def dashboard():
    now = datetime.utcnow()
    online_threshold = now - timedelta(seconds=10)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agents ORDER BY name ASC")
    agents_rows = cur.fetchall()
    cur.execute("SELECT * FROM employees")
    emps_rows = cur.fetchall()
    conn.close()

    emp_by_agent = {e["agent_name"]: e for e in emps_rows}

    agents = []
    for a in agents_rows:
        name = a["name"]
        last_seen = datetime.fromisoformat(a["last_seen"])
        online = last_seen >= online_threshold

        emp = emp_by_agent.get(name)
        full_name = emp["full_name"] if emp and emp["full_name"] else None
        department = emp["department"] if emp else None
        role = emp["role"] if emp else None

        agents.append(
            {
                "name": name,
                "last_seen": last_seen,
                "online": online,
                "full_name": full_name,
                "department": department,
                "role": role,
                "active_window": a["active_window"],
                "active_process": a["active_process"],
            }
        )

    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>BestHome Monitor - Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                margin: 0;
                background: #020617;
                color: #e5e7eb;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 16px;
                background: #020617;
                border-bottom: 1px solid #111827;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .brand { display: flex; align-items: center; gap: 8px; }
            .badge {
                width: 28px; height: 28px; border-radius: 999px;
                background: radial-gradient(circle at 30% 0%, #bbf7d0, #22c55e);
                display: flex; align-items: center; justify-content: center;
                font-size: 16px; color: #022c22;
            }
            .subtitle { font-size: 12px; color: #9ca3af; }
            .logout-btn {
                font-size: 13px; color: #9ca3af; text-decoration: none;
                border-radius: 999px; padding: 6px 10px; border: 1px solid #1f2937;
                display: inline-flex; align-items: center; gap: 6px;
            }
            .logout-btn:hover { border-color: #ef4444; color: #fecaca; }
            main { padding: 16px; }

            /* Top stats */
            .stats-box { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
            .stat-item {
                background:#111827; padding:8px 14px; border-radius:8px;
                font-size:14px; border:1px solid #1f2937;
            }
            .stat-online {
                background:rgba(34,197,94,0.2);
                border-color:rgba(34,197,94,0.5);
                color:#bbf7d0;
            }
            .stat-offline {
                background:rgba(239,68,68,0.15);
                border-color:rgba(239,68,68,0.4);
                color:#fecaca;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
                gap: 16px;
            }
            .card {
                background: #020617;
                border-radius: 12px;
                border: 1px solid #111827;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .card-header {
                padding: 10px 12px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid #111827;
            }
            .name { font-size: 14px; font-weight: 600; }
            .emp-line { font-size: 12px; color: #9ca3af; }
            .status {
                font-size: 11px; padding: 2px 8px; border-radius: 999px;
                display: inline-flex; align-items:center; gap:4px;
            }
            .online {
                background: rgba(34,197,94,0.15);
                color: #bbf7d0;
                border: 1px solid rgba(34,197,94,0.6);
            }
            .offline {
                background: rgba(248,113,113,0.12);
                color: #fecaca;
                border: 1px solid rgba(239,68,68,0.5);
            }
            .card-body { padding: 10px 12px 12px; }
            .meta { font-size: 11px; color: #9ca3af; margin-bottom: 4px; }
            .small { font-size: 11px; color: #9ca3af; margin-bottom: 8px; }
            .view-link {
                display: inline-flex; align-items:center; gap:6px;
                font-size: 12px; text-decoration:none;
                color: #22c55e; padding:6px 10px;
                border-radius:999px; border:1px solid rgba(34,197,94,0.4);
            }
            .view-link:hover { background: rgba(34,197,94,0.1); }

            .live-thumb {
                width:100%; border-radius:8px;
                border:1px solid #111827;
                max-height:150px; object-fit:cover;
                margin:10px 0;
            }

        </style>
    </head>
    <body>
        <header>
            <div class="brand">
                <div class="badge">BH</div>
                <div>
                    <div style="font-size:14px; font-weight:600;">BestHome Monitor</div>
                    <div class="subtitle">İşçi komputerlərinin canlı izlənməsi</div>
                </div>
            </div>
            <a href="{{ url_for('logout') }}" class="logout-btn">Çıxış</a>
        </header>

        <main>

            <!-- ==== ÜMUMİ STATİSTİKALAR ==== -->
            <div class="stats-box">
                <div class="stat-item">Ümumi: <b>{{ agents|length }}</b></div>
                <div class="stat-item stat-online">Online: <b>{{ agents|selectattr('online')|list|length }}</b></div>
                <div class="stat-item stat-offline">Offline: <b>{{ agents|rejectattr('online')|list|length }}</b></div>
            </div>

            <div class="topbar" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <div style="font-size:14px; font-weight:500;">Agentlər ({{ agents|length }})</div>
                <a href="{{ url_for('employees') }}" class="btn-secondary">👥 İşçi paneli</a>
            </div>

            <div class="grid">
                {% for a in agents %}
                    <div class="card">
                        <div class="card-header">
                            <div>
                                <div class="name">
                                    {% if a.full_name %}{{ a.full_name }}{% else %}{{ a.name }}{% endif %}
                                </div>
                                <div class="emp-line">
                                    PC: {{ a.name }}
                                    {% if a.department %} • {{ a.department }}{% endif %}
                                    {% if a.role %} • {{ a.role }}{% endif %}
                                </div>
                            </div>
                            {% if a.online %}
                                <div class="status online"><span style="width:8px;height:8px;border-radius:999px;background:#4ade80;"></span>ONLINE</div>
                            {% else %}
                                <div class="status offline"><span style="width:8px;height:8px;border-radius:999px;background:#f97373;"></span>OFFLINE</div>
                            {% endif %}
                        </div>

                        <div class="card-body">

                            <div class="meta">Son aktivlik: {{ a.last_seen.strftime('%Y-%m-%d %H:%M:%S') }}</div>
                            <div class="small">
                                Aktiv pəncərə: {{ a.active_window or '—' }}<br>
                                Aktiv proses: {{ a.active_process or '—' }}
                            </div>

                            {% if a.online %}
                            <img src="/screens/{{ a.name }}_last.jpg?t={{ a.last_seen.timestamp() }}"
                                 class="live-thumb"
                                 id="live_{{ a.name }}">
                            {% endif %}

                            <a href="{{ url_for('agent_detail', agent_name=a.name) }}" class="view-link">🔍 Agent səhifəsi</a>
                        </div>
                    </div>
                {% endfor %}
            </div>
        </main>

        <script>
            function refreshLive() {
                {% for a in agents %}
                    {% if a.online %}
                        var img = document.getElementById("live_{{ a.name }}");
                        if (img) { img.src = "/screens/{{ a.name }}_last.jpg?t=" + new Date().getTime(); }
                    {% endif %}
                {% endfor %}
            }
            setInterval(refreshLive, 1000);
        </script>

    </body>
    </html>
    """

    return render_template_string(html, agents=agents)


# ==============================
#   İŞÇİ PANELİ
# ==============================


@app.route("/employees", methods=["GET", "POST"])
@login_required
def employees():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        agent_name = request.form.get("agent_name")
        full_name = request.form.get("full_name")
        department = request.form.get("department")
        role = request.form.get("role")
        note = request.form.get("note")

        cur.execute(
            """
            INSERT INTO employees (agent_name, full_name, department, role, note)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_name)
            DO UPDATE SET
                full_name=excluded.full_name,
                department=excluded.department,
                role=excluded.role,
                note=excluded.note
            """,
            (agent_name, full_name, department, role, note),
        )
        conn.commit()
        return redirect(url_for("employees"))

    # AGENT siyahısı
    cur.execute("SELECT * FROM agents ORDER BY name ASC")
    agents_rows = cur.fetchall()

    # EMPLOYEE məlumatları
    cur.execute("SELECT * FROM employees")
    emps_rows = cur.fetchall()
    conn.close()

    emp_map = {e["agent_name"]: e for e in emps_rows}

    rows = []
    for a in agents_rows:
        agent_name = a["name"]
        e = emp_map.get(agent_name)

        rows.append(
            {
                "agent_name": agent_name,
                "full_name": e["full_name"] if e else "",
                "department": e["department"] if e else "",
                "role": e["role"] if e else "",
                "note": e["note"] if e else "",
            }
        )

    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>İşçi paneli - BestHome Monitor</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { margin:0; background:#020617; color:#e5e7eb; font-family:system-ui; }
            header {
                display:flex; justify-content:space-between; align-items:center;
                padding:10px 12px; border-bottom:1px solid #111827;
                background:#020617; position:sticky; top:0; z-index:10;
            }
            a { color:#22c55e; text-decoration:none; }
            .back {
                font-size:12px; padding:6px 10px; border-radius:999px;
                border:1px solid #1f2937;
            }
            .back:hover { border-color:#22c55e; }
            main { padding:12px; }
            h1 { font-size:16px; margin:0 0 8px; }
            table { width:100%; border-collapse:collapse; font-size:12px; }
            th, td { border-bottom:1px solid #111827; padding:6px; }
            th { color:#9ca3af; font-weight:500; }
            input, textarea {
                width:100%; padding:6px 8px; border-radius:8px;
                border:1px solid #1f2937; background:#020617;
                color:#e5e7eb; font-size:12px;
            }
            input:focus, textarea:focus {
                outline:none; border-color:#22c55e;
            }
            button {
                padding:6px 10px; border-radius:999px;
                border:none; background:#22c55e; color:#02140b;
                font-size:12px; font-weight:500; cursor:pointer;
            }
            button:hover { background:#16a34a; }
        </style>
    </head>
    <body>
        <header>
            <a href="{{ url_for('dashboard') }}" class="back">← Dashboard</a>
            <div style="font-size:13px; color:#9ca3af;">İşçi paneli</div>
        </header>

        <main>
            <h1>Agentlərə işçi bağlama</h1>

            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Agent PC</th>
                        <th>İşçi adı</th>
                        <th>Şöbə</th>
                        <th>Vəzifə</th>
                        <th>Qeyd</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in rows %}
                    <tr>
                        <form method="POST">
                            <td>{{ loop.index }}</td>
                            <td>
                                <input type="text" value="{{ r.agent_name }}" readonly>
                                <input type="hidden" name="agent_name" value="{{ r.agent_name }}">
                            </td>
                            <td><input name="full_name" value="{{ r.full_name }}"></td>
                            <td><input name="department" value="{{ r.department }}"></td>
                            <td><input name="role" value="{{ r.role }}"></td>
                            <td><textarea name="note">{{ r.note }}</textarea></td>
                            <td><button type="submit">Yadda saxla</button></td>
                        </form>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </main>
    </body>
    </html>
    """
    return render_template_string(html, rows=rows)


# ==============================
#   AGENT DETAIL + 1 SAAT LOG + QALEREYA LINK
# ==============================


@app.route("/agent/<agent_name>")
@login_required
def agent_detail(agent_name):
    now = datetime.utcnow()
    since_1h = now - timedelta(hours=1)

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM agents WHERE name = ?", (agent_name,))
    a = cur.fetchone()
    if not a:
        conn.close()
        return f"Agent tapılmadı: {agent_name}", 404

    cur.execute("SELECT * FROM employees WHERE agent_name = ?", (agent_name,))
    emp = cur.fetchone()
    conn.close()

    last_seen = datetime.fromisoformat(a["last_seen"])
    is_online = last_seen >= datetime.utcnow() - timedelta(seconds=10)

    full_name = emp["full_name"] if emp and emp["full_name"] else agent_name
    department = emp["department"] if emp else ""
    role = emp["role"] if emp else ""
    note = emp["note"] if emp else ""

    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{{ full_name }} - BestHome Monitor</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { margin:0; background:#020617; color:#e5e7eb; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
            header {
                display:flex; justify-content:space-between; align-items:center;
                padding:10px 12px; background:#020617; border-bottom:1px solid #111827; position:sticky; top:0; z-index:10;
            }
            a { color:#22c55e; text-decoration:none; }
            .back { font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid #1f2937; }
            .back:hover { border-color:#22c55e; }
            main { padding:12px; }
            h1 { font-size:16px; margin:0 0 6px; }
            .pill {
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 999px;
                border: 1px solid #1f2937;
                color: #9ca3af;
            }
            .pill-online {
                border-color: rgba(34,197,94,0.6);
                color: #bbf7d0;
                background: rgba(34,197,94,0.12);
            }
            .pill-offline {
                border-color: rgba(248,113,113,0.6);
                color: #fecaca;
                background: rgba(248,113,113,0.12);
            }
            .live-box {
                background:#020617; border-radius:12px; border:1px solid #111827; padding:10px; margin-bottom:14px;
            }
            .live-header {
                display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;
            }
            .live-img {
                width:100%; max-height:420px; object-fit:contain; border-radius:8px; border:1px solid #111827; background:#020617;
                cursor:pointer;
            }
            .live-meta { font-size:11px; color:#9ca3af; margin-top:4px; }
            .chart-box {
                margin-bottom:14px;
                background:#020617; border-radius:12px; border:1px solid #111827; padding:10px;
            }
            .btn-gallery {
                font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid #1f2937;
                color:#9ca3af; text-decoration:none;
            }
            .btn-gallery:hover { border-color:#22c55e; color:#bbf7d0; }

            /* FULLSCREEN MODAL for live image */
            #modal {
                display:none; position:fixed; inset:0;
                background:rgba(0,0,0,0.9); z-index:9999;
                align-items:center; justify-content:center;
            }
            #modal img {
                max-width:95%; max-height:95%; border-radius:12px;
            }
            #modal-close {
                position:absolute; top:15px; right:15px; cursor:pointer; font-size:24px;
                color:#e5e7eb;
            }
        </style>
    </head>
    <body>
        <header>
            <a href="{{ url_for('dashboard') }}" class="back">← Dashboard</a>
            <div style="font-size:13px; color:#9ca3af;">BestHome Monitor</div>
        </header>
        <main>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                <div>
                    <h1>{{ full_name }}</h1>
                    <div style="font-size:12px; color:#9ca3af; margin-bottom:6px;">
                        PC: {{ agent_name }}
                        {% if department %} • {{ department }}{% endif %}
                        {% if role %} • {{ role }}{% endif %}<br>
                        Son aktivlik: {{ last_seen_str }}
                    </div>
                    <div style="font-size:12px; color:#9ca3af; margin-bottom:8px;">
                        Aktiv pəncərə: {{ active_window or '—' }}<br>
                        Aktiv proses: {{ active_process or '—' }}
                    </div>
                    {% if note %}
                    <div style="font-size:12px; color:#9ca3af; margin-bottom:10px;">
                        Qeyd: {{ note }}
                    </div>
                    {% endif %}
                </div>
                <div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px;">
                    {% if is_online %}
                    <span class="pill pill-online">● ONLINE</span>
                    {% else %}
                    <span class="pill pill-offline">● OFFLINE</span>
                    {% endif %}
                    <a href="{{ url_for('agent_gallery', agent_name=agent_name) }}" class="btn-gallery">
                        📸 Son 1 saatlıq qalereya
                    </a>
                </div>
            </div>

            <div class="live-box">
                <div class="live-header">
                    <div style="font-size:13px; font-weight:500;">Canlı görüntü (0.5s interval)</div>
                    <div id="live-status" style="font-size:11px; color:#9ca3af;">Yüklənir...</div>
                </div>
                <img id="live-img" class="live-img" src="" alt="Live screenshot">
                <div class="live-meta" id="live-meta"></div>
            </div>

            <div class="chart-box">
                <div style="font-size:13px; font-weight:500; margin-bottom:4px;">Son 1 saat aktivlik qrafiki</div>
                <canvas id="activityChart" height="120"></canvas>
            </div>
        </main>

        <!-- FULLSCREEN MODAL -->
        <div id="modal">
            <span id="modal-close">✕</span>
            <img id="modal-img">
        </div>

        <script>
            const agentName = "{{ agent_name }}";
            const imgEl = document.getElementById("live-img");
            const metaEl = document.getElementById("live-meta");
            const statusEl = document.getElementById("live-status");

            async function fetchLive() {
                try {
                    const resp = await fetch("/api/agent/" + encodeURIComponent(agentName) + "/last");
                    if (!resp.ok) {
                        statusEl.textContent = "Görüntü yoxdur";
                        return;
                    }
                    const data = await resp.json();
                    if (!data.ok) {
                        statusEl.textContent = "Görüntü yoxdur";
                        return;
                    }
                    const now = new Date().getTime();
                    imgEl.src = "/screens/" + data.filename + "?t=" + now;
                    metaEl.textContent = "Son görüntü: " + data.created_at;
                    statusEl.textContent = "Aktiv";
                } catch (e) {
                    statusEl.textContent = "Bağlantı xətası";
                }
            }

            fetchLive();
            setInterval(fetchLive, 500);  // 0.5 saniyə

            // Chart – son 1 saat
            async function loadChart() {
                try {
                    const resp = await fetch("/api/agent/" + encodeURIComponent(agentName) + "/stats1h");
                    if (!resp.ok) return;
                    const data = await resp.json();
                    const ctx = document.getElementById('activityChart').getContext('2d');
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: data.labels,
                            datasets: [{
                                label: 'Screenshot sayı',
                                data: data.data,
                                borderWidth: 1,
                                tension: 0.2
                            }]
                        },
                        options: {
                            plugins: {
                                legend: {
                                    labels: { color: '#e5e7eb', font: { size: 10 } }
                                }
                            },
                            scales: {
                                x: {
                                    ticks: { color: '#9ca3af', maxRotation: 60, minRotation: 60, font:{size:8} },
                                    grid: { color: '#111827' }
                                },
                                y: {
                                    ticks: { color: '#9ca3af', stepSize: 1 },
                                    grid: { color: '#111827' }
                                }
                            }
                        }
                    });
                } catch (e) { }
            }
            loadChart();

            // Live image fullscreen modal
            const modal = document.getElementById("modal");
            const modalImg = document.getElementById("modal-img");
            const modalClose = document.getElementById("modal-close");

            imgEl.addEventListener("click", () => {
                if (!imgEl.src) return;
                modalImg.src = imgEl.src;
                modal.style.display = "flex";
            });

            modalClose.addEventListener("click", () => {
                modal.style.display = "none";
            });

            modal.addEventListener("click", (e) => {
                if (e.target === modal) {
                    modal.style.display = "none";
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(
        html,
        agent_name=agent_name,
        full_name=full_name,
        department=department,
        role=role,
        note=note,
        last_seen_str=last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        is_online=is_online,
        active_window=a["active_window"],
        active_process=a["active_process"],
    )


# ==============================
#   QALEREYA – SON 1 SAAT, LAZY LOAD + FULLSCREEN
# ==============================


@app.route("/agent/<agent_name>/gallery")
@login_required
def agent_gallery(agent_name):
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{{ agent_name }} - Qalereya</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { margin:0; background:#020617; color:#e5e7eb; font-family:system-ui,-apple-system,"Segoe UI"; }
            header {
                padding:10px 12px; border-bottom:1px solid #111827;
                display:flex; justify-content:space-between; align-items:center;
                background:#020617; position:sticky; top:0; z-index:20;
            }
            a { color:#22c55e; text-decoration:none; }
            .back { font-size:12px; padding:6px 10px; border-radius:999px; border:1px solid #1f2937; }
            .back:hover { border-color:#22c55e; }
            .grid {
                display:grid;
                grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
                gap:8px; padding:10px;
            }
            .shot {
                background:#020617; border:1px solid #111827; border-radius:8px;
                padding:4px; cursor:pointer; font-size:11px; color:#9ca3af;
            }
            .shot img {
                width:100%; height:120px; object-fit:cover; border-radius:6px;
                margin-bottom:4px;
            }

            /* FULLSCREEN MODAL */
            #modal {
                display:none; position:fixed; inset:0;
                background:rgba(0,0,0,0.9); z-index:9999;
                align-items:center; justify-content:center;
            }
            #modal img {
                max-width:95%; max-height:95%; border-radius:12px;
            }
            #modal-close {
                position:absolute; top:15px; right:15px; cursor:pointer; font-size:24px; color:#e5e7eb;
            }
        </style>
    </head>
    <body>
        <header>
            <a class="back" href="{{ url_for('agent_detail', agent_name=agent_name) }}">← Agent səhifəsi</a>
            <div style="font-size:13px; color:#9ca3af;">Son 1 saatlıq qalereya</div>
        </header>

        <div id="gallery" class="grid"></div>

        <div id="modal">
            <span id="modal-close">✕</span>
            <img id="modal-img">
        </div>

        <script>
            const agent = "{{ agent_name }}";
            let offset = 0;
            const limit = 60;
            let isLoading = false;
            const gallery = document.getElementById("gallery");

            async function loadMore() {
                if (isLoading) return;
                isLoading = true;
                const res = await fetch(`/api/agent/${encodeURIComponent(agent)}/shots?offset=${offset}&limit=${limit}`);
                const data = await res.json();
                if (data.length === 0) {
                    window.removeEventListener("scroll", scrollHandler);
                    isLoading = false;
                    return;
                }
                data.forEach(item => {
                    const div = document.createElement("div");
                    div.className = "shot";
                    div.innerHTML = `
                        <img src="/screens/${item.filename}">
                        <div>${item.created_at}</div>
                    `;
                    div.addEventListener("click", () => openModal(item.filename));
                    gallery.appendChild(div);
                });
                offset += data.length;
                isLoading = false;
            }

            function scrollHandler() {
                if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
                    loadMore();
                }
            }

            window.addEventListener("scroll", scrollHandler);
            loadMore();

            // FULLSCREEN MODAL
            const modal = document.getElementById("modal");
            const modalImg = document.getElementById("modal-img");
            const modalClose = document.getElementById("modal-close");

            function openModal(filename) {
                modalImg.src = "/screens/" + filename;
                modal.style.display = "flex";
            }

            modalClose.addEventListener("click", () => {
                modal.style.display = "none";
            });

            modal.addEventListener("click", (e) => {
                if (e.target === modal) {
                    modal.style.display = "none";
                }
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html, agent_name=agent_name)


# ==============================
#   MAIN
# ==============================


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5050, debug=False)
