# Consent Monitor Dashboard

Legal, consent-based remote screen monitoring dashboard for computers you own or manage. The client is intentionally visible and includes local pause, resume, and exit controls.

## Safety boundaries

This project does **not** implement stealth, hidden monitoring, persistence without consent, keylogging, remote shell, arbitrary command execution, or shutdown commands. Every device must be enrolled by an administrator-generated token, and uploads without a valid Bearer token are rejected.

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set strong values.
3. Generate an admin password hash:
   ```bash
   python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
   ```
4. Start the server locally:
   ```bash
   flask --app server run --host 0.0.0.0 --port 5000
   ```
5. Login, open **Cihaz tokeni**, create a token, and copy it once.
6. On each company-managed PC, set client environment variables:
   ```powershell
   setx SERVER_URL "https://your-server.example.com"
   setx DEVICE_TOKEN "paste-token-here"
   setx DEVICE_NAME "FINANCE-PC-01"
   setx INTERVAL "0.5"
   ```
7. Run the visible client:
   ```bash
   python client.py
   ```

## Render-compatible start command

Use a production WSGI server and HTTPS at the platform/load-balancer layer:

```bash
waitress-serve --host=0.0.0.0 --port=$PORT server:app
```

Set `SESSION_COOKIE_SECURE=true` in HTTPS deployments.

## PyInstaller client build

On the target desktop OS after setting up dependencies:

```bash
pyinstaller --onefile --windowed --name ConsentMonitorAgent client.py
```

The resulting app still opens a visible window titled `Monitor aktivdir`.

## Main features

- Secure Flask sessions with environment-based `SECRET_KEY`, HTTP-only/SameSite cookies, optional secure cookies, CSRF protection, login rate limiting, and security headers.
- Admin email/password or password hash from environment variables.
- Device enrollment with one-time token display; clients authenticate with `Authorization: Bearer <DEVICE_TOKEN>`.
- Audit logs for login, failed login, logout, device enrollment, screen viewing, pause, employee updates, and video creation.
- Premium dark Azerbaijani dashboard with live cards, search, status/department filters, detail viewer, fullscreen mode, and last-five-minutes gallery.
- Screenshot retention cleanup keeps only the last five minutes of stored frames while preserving latest preview files.
- Optional OpenCV video endpoint for the last five minutes; returns a clear error if dependencies are missing.
