"""Consent-based desktop screen sharing agent.

This client is intentionally visible: it opens a small status window titled
"Monitor aktivdir" and lets the local user pause, resume, or exit sharing.
It does not provide persistence, stealth behavior, remote shell, keylogging,
shutdown, or arbitrary command execution.
"""

import getpass
import io
import logging
import os
import platform
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests
import tkinter as tk
from PIL import Image, ImageGrab
from tkinter import messagebox, ttk

try:
    import psutil
except ImportError:  # optional but recommended
    psutil = None

CLIENT_VERSION = "2.0.0-consent"
DEFAULT_INTERVAL = 0.5
MIN_INTERVAL = 0.5
MAX_INTERVAL = 10.0
PREVIEW_MAX_WIDTH = int(os.environ.get("PREVIEW_MAX_WIDTH", "1280"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "68"))
LOG_PATH = Path(os.environ.get("MONITOR_LOG_PATH", Path.home() / "consent_monitor_agent.log"))

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("consent-monitor-agent")


@dataclass
class AgentConfig:
    server_url: str
    device_token: str
    device_name: str
    interval: float = DEFAULT_INTERVAL

    @classmethod
    def from_env(cls) -> "AgentConfig":
        server_url = os.environ.get("SERVER_URL", "").strip().rstrip("/")
        device_token = os.environ.get("DEVICE_TOKEN", "").strip()
        device_name = os.environ.get("DEVICE_NAME", platform.node() or socket.gethostname() or "Managed-PC").strip()
        try:
            interval = max(MIN_INTERVAL, float(os.environ.get("INTERVAL", DEFAULT_INTERVAL)))
        except ValueError:
            interval = DEFAULT_INTERVAL
        if not server_url:
            raise ValueError("SERVER_URL mühit dəyişəni təyin edilməlidir")
        if not device_token:
            raise ValueError("DEVICE_TOKEN mühit dəyişəni təyin edilməlidir")
        return cls(server_url=server_url, device_token=device_token, device_name=device_name, interval=interval)


def get_active_info() -> Tuple[str, str]:
    if platform.system().lower() != "windows":
        return "Bilinmir", "Bilinmir"
    try:
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) or "Bilinmir"
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = "Bilinmir"
        if psutil:
            process = psutil.Process(pid).name()
        return title[:500], process[:180]
    except Exception as exc:
        logger.debug("Active window lookup failed: %s", exc)
        return "Bilinmir", "Bilinmir"


def os_description() -> str:
    return f"{platform.system()} {platform.release()} ({platform.version()})"[:180]


def compress_screenshot() -> io.BytesIO:
    image = ImageGrab.grab()
    if PREVIEW_MAX_WIDTH and image.width > PREVIEW_MAX_WIDTH:
        ratio = PREVIEW_MAX_WIDTH / float(image.width)
        image = image.resize((PREVIEW_MAX_WIDTH, int(image.height * ratio)), Image.Resampling.LANCZOS)
    if image.mode != "RGB":
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    buf.seek(0)
    return buf


class ConsentMonitorApp:
    def __init__(self, root: tk.Tk, config: AgentConfig) -> None:
        self.root = root
        self.config = config
        self.paused = threading.Event()
        self.stop_event = threading.Event()
        self.status_queue: "queue.Queue[tuple]" = queue.Queue()
        self.current_interval = config.interval
        self.last_upload = "Heç vaxt"
        self.online = False

        root.title("Monitor aktivdir")
        root.geometry("410x260")
        root.minsize(390, 240)
        root.protocol("WM_DELETE_WINDOW", self.on_exit)

        self.status_var = tk.StringVar(value="Başlayır...")
        self.online_var = tk.StringVar(value="Offline")
        self.last_upload_var = tk.StringVar(value=self.last_upload)
        self.interval_var = tk.StringVar(value=f"{self.current_interval:.1f}s")
        self.paused_var = tk.StringVar(value="Paylaşım aktivdir")

        self.build_ui()
        self.worker = threading.Thread(target=self.capture_loop, name="screen-uploader", daemon=True)
        self.worker.start()
        self.root.after(250, self.process_status_queue)
        logger.info("Consent monitor started for device_name=%s server=%s", config.device_name, config.server_url)

    def build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="Monitor aktivdir", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            frame,
            text="Bu şirkət idarəetməsində olan kompüterdə ekran paylaşımı görünən və razılıq əsaslıdır.",
            wraplength=360,
        ).pack(anchor="w", pady=(4, 12))

        grid = ttk.Frame(frame)
        grid.pack(fill="x")
        rows = [
            ("Status", self.online_var),
            ("Son yükləmə", self.last_upload_var),
            ("Interval", self.interval_var),
            ("Paylaşım", self.paused_var),
        ]
        for row, (label, var) in enumerate(rows):
            ttk.Label(grid, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(grid, textvariable=var).grid(row=row, column=1, sticky="w", padx=(10, 0), pady=2)

        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="#2563eb")
        self.status_label.pack(anchor="w", pady=(10, 12))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Pause sharing", command=self.pause).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Resume sharing", command=self.resume).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Exit", command=self.on_exit).pack(side="right")

    def pause(self) -> None:
        self.paused.set()
        self.status_queue.put(("paused", "Paylaşım pauzaya qoyuldu"))
        logger.info("User paused screen sharing")

    def resume(self) -> None:
        self.paused.clear()
        self.status_queue.put(("resumed", "Paylaşım bərpa edildi"))
        logger.info("User resumed screen sharing")

    def on_exit(self) -> None:
        if messagebox.askokcancel("Monitor aktivdir", "Ekran paylaşım agentini dayandırmaq istəyirsiniz?"):
            self.stop_event.set()
            logger.info("User exited screen sharing agent")
            self.root.after(200, self.root.destroy)

    def metadata(self, status: str) -> dict:
        active_window, active_process = get_active_info()
        return {
            "pc_name": self.config.device_name,
            "username": getpass.getuser(),
            "os": os_description(),
            "active_window": active_window,
            "active_process": active_process,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_version": CLIENT_VERSION,
            "status": status,
        }

    def upload_once(self, status: str = "online") -> None:
        headers = {
            "Authorization": f"Bearer {self.config.device_token}",
            "X-Client-Version": CLIENT_VERSION,
        }
        files = None
        if status != "paused":
            screenshot = compress_screenshot()
            files = {"screenshot": ("screen.jpg", screenshot, "image/jpeg")}
        response = requests.post(
            f"{self.config.server_url}/upload",
            data=self.metadata(status),
            files=files,
            headers=headers,
            timeout=8,
        )
        response.raise_for_status()

    def capture_loop(self) -> None:
        consecutive_failures = 0
        sent_pause_notice = False
        while not self.stop_event.is_set():
            try:
                if self.paused.is_set():
                    if not sent_pause_notice:
                        self.upload_once(status="paused")
                        sent_pause_notice = True
                    self.status_queue.put(("paused", "Paylaşım pauzadadır"))
                    time.sleep(1.0)
                    continue

                sent_pause_notice = False
                self.upload_once(status="online")
                consecutive_failures = 0
                self.current_interval = max(MIN_INTERVAL, self.config.interval)
                self.status_queue.put(("online", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            except Exception as exc:
                consecutive_failures += 1
                self.current_interval = min(MAX_INTERVAL, max(self.config.interval, 2 ** min(consecutive_failures, 4) * 0.5))
                self.status_queue.put(("offline", str(exc)[:120]))
                logger.warning("Upload failed; retrying with backoff interval %.1fs: %s", self.current_interval, exc)
            self.stop_event.wait(self.current_interval)

    def process_status_queue(self) -> None:
        while True:
            try:
                kind, value = self.status_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "online":
                self.online_var.set("Online")
                self.last_upload_var.set(value)
                self.status_var.set("Serverə uğurla göndərildi")
            elif kind == "offline":
                self.online_var.set("Offline")
                self.status_var.set(f"Bağlantı xətası: {value}")
            elif kind == "paused":
                self.paused_var.set("Pauzada")
                self.status_var.set(value)
            elif kind == "resumed":
                self.paused_var.set("Paylaşım aktivdir")
                self.status_var.set(value)
            self.interval_var.set(f"{self.current_interval:.1f}s")
        self.root.after(250, self.process_status_queue)


def main() -> int:
    try:
        config = AgentConfig.from_env()
    except Exception as exc:
        logger.error("Configuration error: %s", exc)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Monitor aktivdir", f"Konfiqurasiya xətası: {exc}")
        return 2

    root = tk.Tk()
    style = ttk.Style(root)
    if sys.platform.startswith("win"):
        style.theme_use("vista")
    ConsentMonitorApp(root, config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
