"""Joyeuse Flasher v3 (Offline) - Redmi Note 9 Pro (joyeuse) بواجهة عصرية (CustomTkinter).

- كتخدم أوفلاين: كتقلب على platform-tools وROMs محلياً (الانترنت اختياري)
- معلومات الجهاز، Reboot، فلاش Recovery وBoot (Magisk)
- تبويب التطبيقات: Debloat مع استرجاع، تثبيت وتصدير APK

الأماكن اللي كتقلب فيها الأداة (بالترتيب):
  platform-tools:  <exe>/platform-tools  |  <exe>/joyeuse_data/platform-tools
                   ولا ملف platform-tools*.zip بجنب الـ exe (كيتفك أوتوماتيكيا)
  ROMs:            <exe>/roms  |  <exe>/joyeuse_data/roms
                   (ملفات .tgz/.zip ولا فولدرات فيها flash_all.bat)
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
from tkinter import filedialog, messagebox
import customtkinter as ctk

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
WORK_DIR = os.path.join(APP_DIR, "joyeuse_data")
ROMS_DIR = os.path.join(WORK_DIR, "roms")
PT_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
ROMS_JSON_URL = "https://raw.githubusercontent.com/czaki4694-hub/joyeuse-flasher/main/roms.json"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
EXE_EXT = ".exe" if os.name == "nt" else ""
ARCHIVE_RE = r"\.(tgz|tar\.gz|tar|zip)$"

os.makedirs(ROMS_DIR, exist_ok=True)

DEBLOAT_LOG = os.path.join(WORK_DIR, "debloat_log.txt")
# تطبيقات ضرورية للنظام: الأداة كترفض تعطيلها (باش مايوقعش bootloop)
PROTECTED = {
    "android", "com.android.systemui", "com.android.phone", "com.android.settings",
    "com.miui.home", "com.android.providers.settings", "com.android.providers.contacts",
    "com.android.providers.telephony", "com.android.providers.media",
    "com.android.packageinstaller", "com.google.android.packageinstaller",
    "com.android.server.telecom", "com.android.shell", "com.miui.securitycenter",
}
# اقتراحات شائعة ديال MIUI (كتختلف حسب النسخة، راجعها قبل التعطيل، والاسترجاع ممكن)
SUGGESTED = {
    "com.miui.analytics", "com.miui.msa.global", "com.miui.bugreport",
    "com.miui.hybrid", "com.miui.hybrid.accessory", "com.xiaomi.mipicks",
    "com.mi.globalbrowser", "com.miui.videoplayer", "com.miui.player",
}

# ---------- الألوان (فاتح, داكن) ----------
ACCENT = "#FF6900"
ACCENT_HOVER = "#E05D00"
DANGER = "#D93025"
DANGER_HOVER = "#B3261E"
BG = ("#F4F5F7", "#18191B")
CARD = ("#FFFFFF", "#202124")
INNER = ("#F6F7F9", "#2A2C30")
SOFT = ("#E9ECF0", "#34373C")
SOFT_HOVER = ("#DCE0E6", "#42464C")
TEXT = ("#1F2328", "#ECEFF4")
MUTED = ("#6B7280", "#9AA0A6")
FONT = "Segoe UI"
MONO = "Consolas"


def find_tools_dir():
    """كيقلب على platform-tools محلياً (مجمّعة مع الـ exe، ولا بجنبو)."""
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(os.path.join(meipass, "platform-tools"))
    cands.append(os.path.join(APP_DIR, "platform-tools"))
    cands.append(os.path.join(WORK_DIR, "platform-tools"))
    for d in cands:
        if os.path.exists(os.path.join(d, "fastboot" + EXE_EXT)):
            return d
    return os.path.join(WORK_DIR, "platform-tools")


def tool(name):
    return os.path.join(find_tools_dir(), name + EXE_EXT)


def fastboot_exe():
    return tool("fastboot")


def adb_exe():
    return tool("adb")


def has_flash_script(folder):
    for _, _, files in os.walk(folder):
        if "flash_all.bat" in files:
            return True
    return False


def find_rom_root(folder):
    for dp, _, files in os.walk(folder):
        if "flash_all.bat" in files:
            return dp
    return folder


def scan_local_roms():
    """كيرجع ROMs لقاها محلياً: [{'name':..., 'path':...}]"""
    found, seen = [], set()
    for base in (os.path.join(APP_DIR, "roms"), ROMS_DIR):
        if not os.path.isdir(base):
            continue
        entries = sorted(os.listdir(base))
        stems = {re.sub(ARCHIVE_RE, "", e) for e in entries if re.search(ARCHIVE_RE, e)}
        for e in entries:
            p = os.path.join(base, e)
            if os.path.abspath(p) in seen:
                continue
            if os.path.isfile(p) and re.search(ARCHIVE_RE, e):
                found.append({"name": f"[محلي] {e}", "path": p})
            elif os.path.isdir(p) and e not in stems and has_flash_script(p):
                found.append({"name": f"[محلي] {e}", "path": p})
            seen.add(os.path.abspath(p))
    return found


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__()
        self.title("Joyeuse Flasher - Redmi Note 9 Pro")
        self.geometry("920x840")
        self.minsize(860, 720)

        self.f_title = ctk.CTkFont(family=FONT, size=24, weight="bold")
        self.f_head = ctk.CTkFont(family=FONT, size=15, weight="bold")
        self.f_body = ctk.CTkFont(family=FONT, size=13)
        self.f_small = ctk.CTkFont(family=FONT, size=12)
        self.f_mono = ctk.CTkFont(family=MONO, size=12)

        self.rom_dir = tk.StringVar()
        self.mode = tk.StringVar(value="flash_all.bat")
        self.url = tk.StringVar()
        self.recovery_path = tk.StringVar()
        self.boot_path = tk.StringVar()
        self.reboot_after = tk.BooleanVar(value=True)
        self.info = tk.StringVar(value="اضغط على 'قراءة المعلومات'.")
        self.status = tk.StringVar(value="الهاتف: غير مكشوف")
        self.roms = []
        self.rom_names = []
        self.pkgs_all = []
        self.pkg_mode = tk.StringVar(value="system")
        self.pkg_filter = tk.StringVar()
        self.busy = False
        self._build_ui()
        self.log("مرحبا. 1) حمل الأدوات 2) حمل/اختار ROM 3) فلاش. ولا استعمل التبويبات الأخرى.")
        threading.Thread(target=self.load_rom_list, daemon=True).start()

    # ---------- مكونات الواجهة ----------
    def button(self, parent, text, command, kind="primary", width=140):
        colors = {
            "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white"),
            "danger": dict(fg_color=DANGER, hover_color=DANGER_HOVER, text_color="white"),
            "soft": dict(fg_color=SOFT, hover_color=SOFT_HOVER, text_color=TEXT),
        }[kind]
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=34,
                             corner_radius=8, font=self.f_body, **colors)

    def entry(self, parent, var, placeholder=""):
        return ctk.CTkEntry(parent, textvariable=var, placeholder_text=placeholder, height=34,
                            corner_radius=8, font=self.f_body)

    def row(self, parent):
        r = ctk.CTkFrame(parent, fg_color="transparent")
        r.pack(fill="x", pady=3)
        return r

    def card(self, parent, title, hint=None, expand=False):
        box = ctk.CTkFrame(parent, corner_radius=12, fg_color=INNER)
        box.pack(fill="both" if expand else "x", expand=expand, padx=6, pady=6)
        ctk.CTkLabel(box, text=title, font=self.f_head, text_color=TEXT).pack(anchor="w", padx=14, pady=(10, 0))
        if hint:
            ctk.CTkLabel(box, text=hint, font=self.f_small, text_color=MUTED, wraplength=760,
                         justify="left").pack(anchor="w", padx=14)
        body = ctk.CTkFrame(box, fg_color="transparent")
        body.pack(fill="both" if expand else "x", expand=expand, padx=12, pady=(6, 12))
        return body

    def _build_ui(self):
        self.configure(fg_color=BG)

        # --- رأس الصفحة ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 4))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Joyeuse Flasher", font=self.f_title, text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(left, text="Redmi Note 9 Pro  •  joyeuse", font=self.f_small,
                     text_color=MUTED).pack(anchor="w")
        self.theme_switch = ctk.CTkSwitch(header, text="داكن", command=self.toggle_theme,
                                          progress_color=ACCENT, font=self.f_body, text_color=TEXT)
        self.theme_switch.pack(side="right")
        ctk.CTkLabel(header, textvariable=self.status, font=self.f_small,
                     text_color=MUTED).pack(side="right", padx=16)

        # --- السجل والتقدم (تحت) ---
        self.log_box = ctk.CTkTextbox(self, height=150, font=self.f_mono, corner_radius=10,
                                      fg_color=CARD, text_color=TEXT)
        self.log_box.pack(side="bottom", fill="x", padx=18, pady=(4, 14))
        self.log_box.configure(state="disabled")
        self.bar = ctk.CTkProgressBar(self, height=8, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(side="bottom", fill="x", padx=18, pady=4)

        # --- التبويبات ---
        self.tabs = ctk.CTkTabview(
            self, fg_color=CARD, corner_radius=14,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=SOFT,
            segmented_button_unselected_hover_color=SOFT_HOVER,
            text_color=TEXT)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=6)

        self._tab_rom(self.tabs.add("ROM"))
        self._tab_device(self.tabs.add("الجهاز"))
        self._tab_images(self.tabs.add("Recovery / Boot"))
        self._tab_apps(self.tabs.add("التطبيقات"))
        self.style_listbox()

    def _tab_rom(self, t):
        c = self.card(t, "1) الأدوات", "كتحمل adb وfastboot من Google مرة وحدة.")
        r = self.row(c)
        self.button(r, "تحميل platform-tools", lambda: self.run_bg(self.get_tools), width=170).pack(side="left", padx=(0, 8))
        self.button(r, "كشف الهاتف", lambda: self.run_bg(self.detect), "soft").pack(side="left")

        c = self.card(t, "2) ROM", "اختار من اللائحة ولا لصق رابط Fastboot ROM، ومن بعد حدد الفولدر.")
        self.combo = ctk.CTkComboBox(c, values=[], state="readonly", height=34, corner_radius=8,
                                     font=self.f_body, dropdown_font=self.f_body,
                                     button_color=ACCENT, button_hover_color=ACCENT_HOVER)
        self.combo.set("اللائحة فارغة: لصق رابط تحت")
        self.combo.pack(fill="x", pady=3)
        r = self.row(c)
        self.entry(r, self.url, "رابط ROM (.tgz / .zip)").pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(r, "تحميل ROM", lambda: self.run_bg(self.download_rom)).pack(side="left")
        r = self.row(c)
        self.entry(r, self.rom_dir, "فولدر ROM (فيه flash_all.bat)").pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(r, "اختيار فولدر", self.pick_dir, "soft").pack(side="left")

        c = self.card(t, "3) الفلاش")
        ctk.CTkRadioButton(c, text="Clean all (كيمسح كلشي)", variable=self.mode, value="flash_all.bat",
                           fg_color=ACCENT, hover_color=ACCENT_HOVER, font=self.f_body,
                           text_color=TEXT).pack(anchor="w", pady=3)
        ctk.CTkRadioButton(c, text="Save user data (كيحافظ على الداتا)", variable=self.mode,
                           value="flash_all_except_storage.bat", fg_color=ACCENT,
                           hover_color=ACCENT_HOVER, font=self.f_body, text_color=TEXT).pack(anchor="w", pady=3)
        self.button(c, "ابدأ الفلاش", self.start_flash, "danger", width=170).pack(anchor="e", pady=(6, 0))

    def _tab_device(self, t):
        c = self.card(t, "معلومات الجهاز", "كتخدم والهاتف فـ Fastboot ولا فـ Android (USB debugging).")
        self.button(c, "قراءة المعلومات", lambda: self.run_bg(self.device_info), width=170).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(c, textvariable=self.info, justify="left", anchor="w", font=self.f_mono,
                     text_color=TEXT).pack(anchor="w", fill="x")

        c = self.card(t, "Reboot", "كيخدم فـ Fastboot وفـ Android.")
        r = self.row(c)
        self.button(r, "Reboot System", lambda: self.run_bg(lambda: self.reboot("system")), "soft").pack(side="left", padx=(0, 8))
        self.button(r, "Reboot Recovery", lambda: self.run_bg(lambda: self.reboot("recovery")), "soft").pack(side="left", padx=(0, 8))
        self.button(r, "Reboot Fastboot", lambda: self.run_bg(lambda: self.reboot("bootloader")), "soft").pack(side="left")

    def _tab_images(self, t):
        c = self.card(t, "فلاش Recovery (TWRP / OrangeFox...)", "خاص الملف يكون ديال joyeuse بالضبط.")
        r = self.row(c)
        self.entry(r, self.recovery_path, "ملف recovery.img").pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(r, "اختيار .img", lambda: self.pick_img(self.recovery_path), "soft").pack(side="left")
        ctk.CTkCheckBox(c, text="Reboot مباشرة لـ Recovery بعد الفلاش (باش مايرجعش الـ stock recovery)",
                        variable=self.reboot_after, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        font=self.f_body, text_color=TEXT).pack(anchor="w", pady=4)
        self.button(c, "فلاش Recovery", self.start_flash_recovery, "danger", width=170).pack(anchor="e")

        c = self.card(t, "فلاش Boot (boot.img معدل ديال Magisk)")
        r = self.row(c)
        self.entry(r, self.boot_path, "ملف boot.img").pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(r, "اختيار .img", lambda: self.pick_img(self.boot_path), "soft").pack(side="left")
        self.button(c, "فلاش Boot", self.start_flash_boot, "danger", width=170).pack(anchor="e", pady=(6, 0))

    def _tab_apps(self, t):
        c = self.card(t, "تطبيقات الهاتف", "كيخدم عبر adb: فعل USB debugging وقبل الطلب فشاشة الهاتف.", expand=True)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x", pady=(0, 4))
        for text, val in (("النظام", "system"), ("المثبتة", "user"), ("المحذوفة (للاسترجاع)", "removed")):
            ctk.CTkRadioButton(top, text=text, variable=self.pkg_mode, value=val, fg_color=ACCENT,
                               hover_color=ACCENT_HOVER, font=self.f_body,
                               text_color=TEXT).pack(side="left", padx=(0, 14))
        self.button(top, "تحميل اللائحة", lambda: self.run_bg(self.load_pkgs), width=130).pack(side="right")
        self.entry(c, self.pkg_filter, "بحث...").pack(fill="x", pady=4)
        lf = ctk.CTkFrame(c, fg_color="transparent")
        lf.pack(fill="both", expand=True)
        sb = ctk.CTkScrollbar(lf)
        sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(lf, selectmode="extended", height=8, exportselection=False,
                             yscrollcommand=sb.set, activestyle="none")
        self.lb.pack(side="left", fill="both", expand=True)
        sb.configure(command=self.lb.yview)
        self.pkg_filter.trace_add("write", lambda *a: self.refresh_pkgs())
        r = self.row(c)
        self.button(r, "تعطيل المحدد", self.start_debloat, "danger", width=120).pack(side="left", padx=(0, 6))
        self.button(r, "استرجاع المحدد", self.start_restore, "soft", width=120).pack(side="left", padx=(0, 6))
        self.button(r, "اقتراحات MIUI", self.select_suggested, "soft", width=120).pack(side="left", padx=(0, 6))
        self.button(r, "تصدير APK", self.start_export, "soft", width=110).pack(side="left", padx=(0, 6))
        self.button(r, "تثبيت APK...", self.start_install, "soft", width=110).pack(side="left")

    def style_listbox(self):
        dark = ctk.get_appearance_mode() == "Dark"
        self.lb.configure(bg="#2A2C30" if dark else "#FFFFFF", fg="#ECEFF4" if dark else "#1F2328",
                          selectbackground=ACCENT, selectforeground="white",
                          highlightthickness=0, borderwidth=0, font=(MONO, 10))

    def toggle_theme(self):
        ctk.set_appearance_mode("dark" if self.theme_switch.get() else "light")
        self.style_listbox()

    def set_status(self, text):
        self.after(0, lambda: self.status.set(text))

    def log(self, msg):
        def _w():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _w)

    def set_progress(self, v):
        self.after(0, lambda: self.bar.set(max(0, min(1, v / 100))))

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.rom_dir.set(d)

    def pick_img(self, var):
        f = filedialog.askopenfilename(filetypes=[("Image", "*.img"), ("All files", "*.*")])
        if f:
            var.set(f)

    def run_bg(self, fn):
        if self.busy:
            self.log("كاين شي عملية خدامة، تسنى حتى توفي.")
            return

        def wrap():
            self.busy = True
            try:
                fn()
            except Exception as e:
                self.log(f"خطأ: {e}")
            finally:
                self.busy = False
        threading.Thread(target=wrap, daemon=True).start()

    # ---------- download helpers (اختياري، كيحتاج انترنت) ----------
    def download(self, url, dest):
        self.log(f"تحميل: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "JoyeuseFlasher/3.0"})
        with urllib.request.urlopen(req, timeout=15) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    self.set_progress(done * 100 / total)
        self.set_progress(0)

    def local_tools_zip(self):
        for base in (APP_DIR, WORK_DIR):
            if os.path.isdir(base):
                for fn in os.listdir(base):
                    if fn.lower().startswith("platform-tools") and fn.lower().endswith(".zip"):
                        return os.path.join(base, fn)
        return None

    def get_tools(self):
        if os.path.exists(fastboot_exe()):
            self.log(f"platform-tools موجودة: {find_tools_dir()}")
            return
        os.makedirs(WORK_DIR, exist_ok=True)
        # 1) zip محلي
        zp = self.local_tools_zip()
        if zp:
            self.log(f"فك الضغط من الملف المحلي: {zp}")
            with zipfile.ZipFile(zp) as z:
                z.extractall(WORK_DIR)
            if os.path.exists(fastboot_exe()):
                self.log("تم تجهيز platform-tools (من الملف المحلي).")
                return
        # 2) تحميل (غير إلا كان الانترنت)
        try:
            zp = os.path.join(WORK_DIR, "platform-tools.zip")
            self.download(PT_URL, zp)
            with zipfile.ZipFile(zp) as z:
                z.extractall(WORK_DIR)
            os.remove(zp)
            self.log("تم تثبيت platform-tools.")
        except Exception:
            raise RuntimeError(
                "platform-tools ما لقيتهاش وما كاينش انترنت.\n"
                f"حط فولدر 'platform-tools' (فيه fastboot.exe وadb.exe) هنا:\n{APP_DIR}\n"
                "ولا حط ملف platform-tools-latest-windows.zip فنفس الفولدر.")

    def ensure_tools(self):
        if not os.path.exists(fastboot_exe()):
            self.get_tools()

    # ---------- ROMs ----------
    def load_rom_list(self):
        remote = []
        try:
            with urllib.request.urlopen(ROMS_JSON_URL, timeout=4) as r:
                remote = json.loads(r.read().decode())
        except Exception:
            local = os.path.join(APP_DIR, "roms.json")
            if os.path.exists(local):
                try:
                    with open(local, encoding="utf-8") as f:
                        remote = json.load(f)
                except Exception:
                    remote = []
        local_roms = scan_local_roms()
        self.roms = local_roms + remote
        self.rom_names = [r["name"] for r in self.roms]

        def _apply():
            self.combo.configure(values=self.rom_names)
            if self.rom_names:
                self.combo.set(self.rom_names[0])
        self.after(0, _apply)
        self.log(f"لائحة ROMs: {len(self.rom_names)} عنصر.")

    def extract_rom(self, src):
        """كيجهز ROM من أرشيف ولا فولدر، وكيحدد rom_dir."""
        if os.path.isdir(src):
            root = find_rom_root(src)
            self.rom_dir.set(root)
            self.log(f"ROM واجد: {root}")
            return
        fname = os.path.basename(src)
        out = os.path.join(ROMS_DIR, re.sub(ARCHIVE_RE, "", fname))
        if os.path.isdir(out) and has_flash_script(out):
            self.log("ROM مفكوك من قبل، غادي نستعملو.")
        else:
            self.log("فك الضغط (ممكن ياخد وقت)...")
            os.makedirs(out, exist_ok=True)
            if fname.endswith(".zip"):
                with zipfile.ZipFile(src) as z:
                    z.extractall(out)
            else:
                with tarfile.open(src, "r:*") as t:
                    t.extractall(out)
        root = find_rom_root(out)
        self.rom_dir.set(root)
        self.log(f"ROM واجد: {root}")

    def download_rom(self):
        url = self.url.get().strip()
        if url:
            fname = url.split("?")[0].rsplit("/", 1)[-1]
            dest = os.path.join(ROMS_DIR, fname)
            if not os.path.exists(dest):
                try:
                    self.download(url, dest)
                except Exception as e:
                    raise RuntimeError(f"التحميل فشل (واش كاين انترنت؟): {e}")
            self.extract_rom(dest)
            return
        name = self.combo.get()
        if name not in self.rom_names:
            raise RuntimeError("اختار ROM من اللائحة، ولا استعمل 'اختيار فولدر'.")
        entry = self.roms[self.rom_names.index(name)]
        if "path" in entry:
            self.extract_rom(entry["path"])
        else:
            fname = entry["url"].split("?")[0].rsplit("/", 1)[-1]
            dest = os.path.join(ROMS_DIR, fname)
            if not os.path.exists(dest):
                try:
                    self.download(entry["url"], dest)
                except Exception as e:
                    raise RuntimeError(f"التحميل فشل (واش كاين انترنت؟): {e}")
            self.extract_rom(dest)

    # ---------- تشغيل الأدوات ----------
    def run_tool(self, exe, args, cwd=None, quiet=False):
        p = subprocess.Popen([exe] + args, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True,
                             creationflags=CREATE_NO_WINDOW)
        out = []
        for line in p.stdout:
            line = line.rstrip()
            out.append(line)
            if not quiet:
                self.log(line)
        p.wait()
        return p.returncode, "\n".join(out)

    def fb(self, args, cwd=None, quiet=False):
        return self.run_tool(fastboot_exe(), args, cwd, quiet)

    def adb(self, args, quiet=False):
        return self.run_tool(adb_exe(), args, None, quiet)

    def fastboot_present(self):
        _, out = self.fb(["devices"], quiet=True)
        return "fastboot" in out

    def adb_present(self):
        _, out = self.adb(["devices"], quiet=True)
        return re.search(r"\tdevice\b", out) is not None

    def getvar(self, name):
        _, out = self.fb(["getvar", name], quiet=True)
        m = re.search(rf"^{re.escape(name)}:\s*(.+)$", out, re.M | re.I)
        return m.group(1).strip() if m else "?"

    def check_device_for_flash(self):
        """كيتأكد بلي الهاتف فـ fastboot، joyeuse، وbootloader مفتوح."""
        self.ensure_tools()
        if not self.fastboot_present():
            raise RuntimeError("ما لقيت هاتف فـ Fastboot. (Vol- + Power ثم ركب الكابل)")
        prod = self.getvar("product")
        if "joyeuse" not in prod.lower():
            raise RuntimeError(f"الهاتف ماشي joyeuse (product: {prod}). توقف الفلاش.")
        if self.getvar("unlocked").lower() == "no":
            raise RuntimeError("الـ bootloader مقفول. خاصك تفتحو قبل.")

    # ---------- الجهاز ----------
    def detect(self):
        self.ensure_tools()
        if not self.fastboot_present():
            self.set_status("الهاتف: ما كاينش")
            self.log("ما لقيت حتى هاتف. دخل الهاتف لـ Fastboot (Vol- + Power) وركب الكابل.")
            return
        prod = self.getvar("product")
        unl = self.getvar("unlocked")
        self.set_status(f"Fastboot • {prod} • unlocked: {unl}")
        self.log(f"product: {prod} | unlocked: {unl}")
        if "joyeuse" not in prod.lower():
            self.log("تحذير: الهاتف ماشي joyeuse!")
        if unl.lower() == "no":
            self.log("تحذير: الـ bootloader مقفول.")

    def device_info(self):
        self.ensure_tools()
        lines = []
        if self.fastboot_present():
            lines.append("الوضع: Fastboot")
            for k in ("product", "unlocked", "anti", "version-bootloader", "serialno", "secure"):
                lines.append(f"{k}: {self.getvar(k)}")
            self.set_status("الهاتف: Fastboot")
        elif self.adb_present():
            lines.append("الوضع: Android (adb)")
            props = [("الموديل", "ro.product.model"), ("الاسم الداخلي", "ro.product.device"),
                     ("Android", "ro.build.version.release"), ("MIUI", "ro.miui.ui.version.name"),
                     ("البناء", "ro.build.version.incremental"), ("Patch", "ro.build.version.security_patch")]
            for label, prop in props:
                _, out = self.adb(["shell", "getprop", prop], quiet=True)
                lines.append(f"{label}: {out.strip() or '?'}")
            self.set_status("الهاتف: Android (adb)")
        else:
            lines.append("ما لقيت حتى هاتف.")
            lines.append("Fastboot: Vol- + Power. Android: فعل USB debugging ووافق على الحاسوب.")
            self.set_status("الهاتف: ما كاينش")
        text = "\n".join(lines)
        self.after(0, lambda: self.info.set(text))
        self.log("تمت قراءة المعلومات.")

    def reboot(self, target):
        self.ensure_tools()
        args = {"system": ["reboot"], "recovery": ["reboot", "recovery"],
                "bootloader": ["reboot", "bootloader"]}[target]
        if self.fastboot_present():
            self.fb(args)
        elif self.adb_present():
            self.adb(args)
        else:
            self.log("ما لقيت حتى هاتف.")

    # ---------- فلاش صور (Recovery / Boot) ----------
    def start_flash_recovery(self):
        self._start_img("recovery", self.recovery_path, self.reboot_after.get())

    def start_flash_boot(self):
        self._start_img("boot", self.boot_path, False)

    def _start_img(self, part, var, then_recovery):
        path = var.get().strip()
        if not os.path.isfile(path):
            messagebox.showerror("خطأ", "اختار ملف .img صحيح.")
            return
        if not path.lower().endswith(".img") and not messagebox.askyesno(
                "تأكيد", "الملف ماشي .img. واش متأكد؟"):
            return
        if not messagebox.askyesno(
                "تأكيد", f"غادي يتفلاش قسم {part} بالملف:\n{os.path.basename(path)}\n\n"
                         "تأكد بلي الملف ديال joyeuse. واش كمل؟"):
            return
        self.run_bg(lambda: self.flash_image(part, path, then_recovery))

    def flash_image(self, part, path, then_recovery):
        self.check_device_for_flash()
        self.log(f"فلاش {part}: {os.path.basename(path)}")
        code, _ = self.fb(["flash", part, path])
        if code != 0:
            raise RuntimeError(f"فلاش {part} فشل (code {code}).")
        self.log(f"تم فلاش {part}.")
        if then_recovery:
            self.log("Reboot لـ Recovery...")
            self.fb(["reboot", "recovery"])

    # ---------- التطبيقات (Debloat / APK) ----------
    def require_adb(self):
        self.ensure_tools()
        _, out = self.adb(["devices"], quiet=True)
        if "unauthorized" in out:
            raise RuntimeError("الهاتف ما واففش على الحاسوب. شوف الشاشة وقبل 'Allow USB debugging'.")
        if not re.search(r"\tdevice\b", out):
            raise RuntimeError("ما لقيت هاتف عبر adb. شغل الهاتف وفعل USB debugging.")

    def pkg_list(self, flags):
        _, out = self.adb(["shell", "pm", "list", "packages"] + flags, quiet=True)
        return {l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")}

    def load_pkgs(self):
        self.require_adb()
        mode = self.pkg_mode.get()
        if mode == "system":
            pk = self.pkg_list(["-s"])
        elif mode == "user":
            pk = self.pkg_list(["-3"])
        else:
            pk = self.pkg_list(["-u"]) - self.pkg_list([])
        self.pkgs_all = sorted(pk)
        self.after(0, self.refresh_pkgs)
        self.log(f"{len(pk)} تطبيق ({mode}).")

    def refresh_pkgs(self):
        q = self.pkg_filter.get().strip().lower()
        self.lb.delete(0, "end")
        for p in self.pkgs_all:
            if q in p.lower():
                self.lb.insert("end", p)

    def selected_pkgs(self):
        return [self.lb.get(i) for i in self.lb.curselection()]

    def select_suggested(self):
        self.lb.selection_clear(0, "end")
        n = 0
        for i in range(self.lb.size()):
            if self.lb.get(i) in SUGGESTED:
                self.lb.selection_set(i)
                n += 1
        self.log(f"تم تحديد {n} تطبيق من الاقتراحات الشائعة (حمل لائحة 'النظام' قبل). راجعهم قبل التعطيل.")

    def start_debloat(self):
        sel = self.selected_pkgs()
        if not sel:
            messagebox.showinfo("تنبيه", "اختار تطبيق واحد على الأقل.")
            return
        if self.pkg_mode.get() == "removed":
            messagebox.showinfo("تنبيه", "هاد اللائحة ديال المحذوفة. استعمل 'استرجاع المحدد'.")
            return
        bad = [p for p in sel if p in PROTECTED]
        if bad:
            messagebox.showerror("ممنوع", "هاد التطبيقات ضرورية للنظام:\n" + "\n".join(bad))
            return
        if not messagebox.askyesno(
                "تأكيد", f"غادي يتعطل {len(sel)} تطبيق (للمستخدم الحالي).\n"
                         "تقدر ترجعهم من 'استرجاع المحدد'.\nواش كمل؟"):
            return
        self.run_bg(lambda: self.do_debloat(sel))

    def do_debloat(self, pkgs):
        self.require_adb()
        ok = []
        for i, p in enumerate(pkgs, 1):
            _, out = self.adb(["shell", "pm", "uninstall", "-k", "--user", "0", p], quiet=True)
            good = "Success" in out
            self.log(f"[{i}/{len(pkgs)}] {p}: " + ("تم" if good else "فشل - " + out.strip()))
            if good:
                ok.append(p)
            self.set_progress(i * 100 / len(pkgs))
        if ok:
            with open(DEBLOAT_LOG, "a", encoding="utf-8") as f:
                f.write("\n".join(ok) + "\n")
        self.log(f"تعطل {len(ok)}/{len(pkgs)}. اللائحة محفوظة فـ {DEBLOAT_LOG}")
        self.set_progress(0)
        self.load_pkgs()

    def start_restore(self):
        sel = self.selected_pkgs()
        if not sel:
            messagebox.showinfo("تنبيه", "اختار تطبيق واحد على الأقل (من لائحة 'المحذوفة').")
            return
        self.run_bg(lambda: self.do_restore(sel))

    def do_restore(self, pkgs):
        self.require_adb()
        n = 0
        for i, p in enumerate(pkgs, 1):
            _, out = self.adb(["shell", "cmd", "package", "install-existing", p], quiet=True)
            good = "installed" in out.lower()
            self.log(f"[{i}/{len(pkgs)}] {p}: " + ("رجع" if good else "فشل - " + out.strip()))
            n += good
            self.set_progress(i * 100 / len(pkgs))
        self.log(f"رجع {n}/{len(pkgs)}.")
        self.set_progress(0)
        self.load_pkgs()

    def start_export(self):
        sel = self.selected_pkgs()
        if not sel:
            messagebox.showinfo("تنبيه", "اختار تطبيق واحد على الأقل.")
            return
        dest = filedialog.askdirectory(title="فين تحفظ ملفات APK؟")
        if dest:
            self.run_bg(lambda: self.do_export(sel, dest))

    def do_export(self, pkgs, dest):
        self.require_adb()
        for i, p in enumerate(pkgs, 1):
            _, out = self.adb(["shell", "pm", "path", p], quiet=True)
            paths = [l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")]
            if not paths:
                self.log(f"{p}: ما لقيت APK")
                continue
            d = os.path.join(dest, p)
            os.makedirs(d, exist_ok=True)
            for path in paths:
                self.adb(["pull", path, d])
            self.set_progress(i * 100 / len(pkgs))
        self.log(f"تم التصدير فـ {dest}")
        self.set_progress(0)

    def start_install(self):
        files = filedialog.askopenfilenames(filetypes=[("APK", "*.apk")])
        if files:
            self.run_bg(lambda: self.do_install(list(files)))

    def do_install(self, files):
        self.require_adb()
        for i, f in enumerate(files, 1):
            self.log(f"[{i}/{len(files)}] تثبيت {os.path.basename(f)}")
            _, out = self.adb(["install", "-r", f])
            if "Success" not in out:
                self.log("فشل التثبيت (الملفات split/.apks/.xapk ما مدعومينش).")
            self.set_progress(i * 100 / len(files))
        self.set_progress(0)

    # ---------- فلاش ROM ----------
    def start_flash(self):
        rd = self.rom_dir.get()
        bat = os.path.join(rd, self.mode.get())
        if not os.path.isfile(bat):
            messagebox.showerror("خطأ", f"ما لقيتش {self.mode.get()} فـ:\n{rd}")
            return
        if "joyeuse" not in open(bat, errors="ignore").read().lower() and \
           not messagebox.askyesno("تأكيد", "ما لقيتش اسم joyeuse فالـ ROM. واش متأكد ROM ديال هاد الهاتف؟"):
            return
        msg = "غادي يتفلاش الهاتف"
        if self.mode.get() == "flash_all.bat":
            msg += " وتتمسح الداتا كاملة"
        if not messagebox.askyesno("تأكيد", msg + ". واش كمل؟\nماتحيدش الكابل حتى يوفي."):
            return
        self.run_bg(lambda: self.flash(rd, bat))

    def flash(self, rd, bat):
        self.check_device_for_flash()
        cmds = []
        for line in open(bat, errors="ignore"):
            s = line.strip()
            if not s.lower().startswith("fastboot"):
                continue
            # حماية: ما كنشغلوش قفل الـ bootloader
            if re.search(r"\b(oem\s+lock|flashing\s+lock)\b", s, re.I):
                self.log(f"تخطي (قفل): {s}")
                continue
            s = s.replace("%*", "").replace("%~dp0", rd + os.sep)
            parts = [p.strip('"') for p in shlex.split(s, posix=False)][1:]
            cmds.append(parts)
        if not cmds:
            raise RuntimeError("ما لقيت حتى أمر fastboot فالسكريبت.")
        for c in cmds:
            for a in c:
                if os.sep in a and not os.path.exists(a):
                    raise RuntimeError(f"ملف ناقص: {a}")
        for i, c in enumerate(cmds, 1):
            self.log(f"[{i}/{len(cmds)}] fastboot {' '.join(os.path.basename(x) for x in c)}")
            code, _ = self.fb(c, cwd=rd)
            if code != 0:
                self.log("توقف الفلاش بسبب خطأ. ماتعاودش تشغل الهاتف حتى تفهم السبب.")
                raise RuntimeError(f"الأمر فشل (code {code})")
            self.set_progress(i * 100 / len(cmds))
        self.log("تم الفلاش بنجاح!")
        self.after(0, lambda: messagebox.showinfo("تم", "الفلاش وفى. الهاتف غيعاود يشغل."))


if __name__ == "__main__":
    App().mainloop()
