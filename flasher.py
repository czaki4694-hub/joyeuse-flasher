"""Joyeuse Flasher v2 - أداة لـ Redmi Note 9 Pro (joyeuse) بالـ fastboot وadb.

- كتحمل platform-tools من Google أوتوماتيكيا
- كتحمل Fastboot ROM من لائحة roms.json (أو من رابط تلصقو) وكتفلاشيه
- معلومات الجهاز، أزرار Reboot، فلاش Recovery وBoot (Magisk)
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import threading
import urllib.request
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
WORK_DIR = os.path.join(APP_DIR, "joyeuse_data")
TOOLS_DIR = os.path.join(WORK_DIR, "platform-tools")
ROMS_DIR = os.path.join(WORK_DIR, "roms")
PT_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
ROMS_JSON_URL = "https://raw.githubusercontent.com/czaki4694-hub/joyeuse-flasher/main/roms.json"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

os.makedirs(ROMS_DIR, exist_ok=True)


def tool(name):
    return os.path.join(TOOLS_DIR, name + (".exe" if os.name == "nt" else ""))


def fastboot_exe():
    return tool("fastboot")


def adb_exe():
    return tool("adb")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Joyeuse Flasher v2 - Redmi Note 9 Pro")
        self.geometry("760x700")
        self.rom_dir = tk.StringVar()
        self.mode = tk.StringVar(value="flash_all.bat")
        self.url = tk.StringVar()
        self.recovery_path = tk.StringVar()
        self.boot_path = tk.StringVar()
        self.reboot_after = tk.BooleanVar(value=True)
        self.info = tk.StringVar(value="اضغط على 'قراءة المعلومات'.")
        self.roms = []
        self.busy = False
        self._build_ui()
        self.log("مرحبا. 1) حمل الأدوات 2) حمل/اختار ROM 3) فلاش. ولا استعمل تبويب الجهاز / Recovery.")
        threading.Thread(target=self.load_rom_list, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        nb = ttk.Notebook(self)
        nb.pack(fill="x", **pad)
        tab_rom = ttk.Frame(nb)
        tab_dev = ttk.Frame(nb)
        tab_img = ttk.Frame(nb)
        nb.add(tab_rom, text="ROM")
        nb.add(tab_dev, text="الجهاز")
        nb.add(tab_img, text="Recovery / Boot")

        # --- تبويب ROM ---
        f1 = ttk.LabelFrame(tab_rom, text="1) الأدوات")
        f1.pack(fill="x", **pad)
        ttk.Button(f1, text="تحميل platform-tools", command=lambda: self.run_bg(self.get_tools)).pack(side="left", **pad)
        ttk.Button(f1, text="كشف الهاتف", command=lambda: self.run_bg(self.detect)).pack(side="left", **pad)

        f2 = ttk.LabelFrame(tab_rom, text="2) ROM")
        f2.pack(fill="x", **pad)
        self.combo = ttk.Combobox(f2, state="readonly", width=70)
        self.combo.pack(fill="x", **pad)
        row = ttk.Frame(f2)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.url).pack(side
