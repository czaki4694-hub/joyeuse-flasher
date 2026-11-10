"""Joyeuse Flasher - أداة تفليش Redmi Note 9 Pro (joyeuse) بالـ fastboot.

- كتحمل platform-tools من Google أوتوماتيكيا
- كتحمل Fastboot ROM من لائحة roms.json (أو من رابط تلصقو)
- كتفك الضغط وكتخدم أوامر flash_all.bat
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
# لائحة ROMs كتتحدث من GitHub بلا ما تعاود تبني exe. بدل USER/REPO ديالك.
ROMS_JSON_URL = "https://raw.githubusercontent.com/USER/REPO/main/roms.json"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

os.makedirs(ROMS_DIR, exist_ok=True)


def fastboot_exe():
    name = "fastboot.exe" if os.name == "nt" else "fastboot"
    return os.path.join(TOOLS_DIR, name)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Joyeuse Flasher - Redmi Note 9 Pro")
        self.geometry("720x560")
        self.rom_dir = tk.StringVar()
        self.mode = tk.StringVar(value="flash_all.bat")
        self.url = tk.StringVar()
        self.roms = []
        self.busy = False
        self._build_ui()
        self.log("مرحبا. الخطوات: 1) حمل الأدوات 2) حمل/اختار ROM 3) فلاش.")
        threading.Thread(target=self.load_rom_list, daemon=True).start()

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        f1 = ttk.LabelFrame(self, text="1) الأدوات")
        f1.pack(fill="x", **pad)
        ttk.Button(f1, text="تحميل platform-tools", command=lambda: self.run_bg(self.get_tools)).pack(side="left", **pad)
        ttk.Button(f1, text="كشف الهاتف", command=lambda: self.run_bg(self.detect)).pack(side="left", **pad)

        f2 = ttk.LabelFrame(self, text="2) ROM")
        f2.pack(fill="x", **pad)
        self.combo = ttk.Combobox(f2, state="readonly", width=70)
        self.combo.pack(fill="x", **pad)
        row = ttk.Frame(f2)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.url).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="حمل (من اللائحة/الرابط)", command=lambda: self.run_bg(self.download_rom)).pack(side="left", **pad)
        row2 = ttk.Frame(f2)
        row2.pack(fill="x")
        ttk.Entry(row2, textvariable=self.rom_dir).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row2, text="اختيار فولدر ROM", command=self.pick_dir).pack(side="left", **pad)

        f3 = ttk.LabelFrame(self, text="3) الفلاش")
        f3.pack(fill="x", **pad)
        ttk.Radiobutton(f3, text="Clean all (كيمسح كلشي)", variable=self.mode, value="flash_all.bat").pack(anchor="w", padx=8)
        ttk.Radiobutton(f3, text="Save user data (كيحافظ على الداتا)", variable=self.mode, value="flash_all_except_storage.bat").pack(anchor="w", padx=8)
        ttk.Button(f3, text="ابدأ الفلاش", command=self.start_flash).pack(anchor="e", **pad)

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", **pad)
        self.txt = scrolledtext.ScrolledText(self, height=15, state="disabled")
        self.txt.pack(fill="both", expand=True, **pad)

    def log(self, msg):
        def _w():
            self.txt.configure(state="normal")
            self.txt.insert("end", msg + "\n")
            self.txt.see("end")
            self.txt.configure(state="disabled")
        self.after(0, _w)

    def set_progress(self, v):
        self.after(0, lambda: self.bar.configure(value=v))

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.rom_dir.set(d)

    def run_bg(self, fn):
        if self.busy:
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

    # ---------- download helpers ----------
    def download(self, url, dest):
        self.log(f"تحميل: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "JoyeuseFlasher/1.0"})
        with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
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

    def get_tools(self):
        if os.path.exists(fastboot_exe()):
            self.log("platform-tools موجودة من قبل.")
            return
        os.makedirs(WORK_DIR, exist_ok=True)
        zp = os.path.join(WORK_DIR, "platform-tools.zip")
        self.download(PT_URL, zp)
        with zipfile.ZipFile(zp) as z:
            z.extractall(WORK_DIR)
        os.remove(zp)
        self.log("تم تثبيت platform-tools.")

    def load_rom_list(self):
        try:
            with urllib.request.urlopen(ROMS_JSON_URL, timeout=10) as r:
                self.roms = json.loads(r.read().decode())
        except Exception:
            local = os.path.join(APP_DIR, "roms.json")
            if os.path.exists(local):
                with open(local, encoding="utf-8") as f:
                    self.roms = json.load(f)
        names = [f"{r['name']}" for r in self.roms]
        self.after(0, lambda: self.combo.configure(values=names))
        if names:
            self.after(0, lambda: self.combo.current(0))
        self.log(f"لائحة ROMs: {len(names)} عنصر.")

    def download_rom(self):
        url = self.url.get().strip()
        if not url:
            i = self.combo.current()
            if i < 0:
                raise RuntimeError("اختار ROM من اللائحة ولا لصق رابط.")
            url = self.roms[i]["url"]
        fname = url.split("?")[0].rsplit("/", 1)[-1]
        dest = os.path.join(ROMS_DIR, fname)
        if not os.path.exists(dest):
            self.download(url, dest)
        self.log("فك الضغط...")
        out = os.path.join(ROMS_DIR, re.sub(r"\.(tgz|tar\.gz|tar|zip)$", "", fname))
        os.makedirs(out, exist_ok=True)
        if fname.endswith(".zip"):
            with zipfile.ZipFile(dest) as z:
                z.extractall(out)
        else:
            with tarfile.open(dest, "r:*") as t:
                t.extractall(out)
        # بعض الأرشيفات فيها فولدر داخلي
        root = out
        for dp, _, files in os.walk(out):
            if "flash_all.bat" in files:
                root = dp
                break
        self.rom_dir.set(root)
        self.log(f"ROM واجد: {root}")

    # ---------- fastboot ----------
    def fb(self, args, cwd=None):
        p = subprocess.Popen([fastboot_exe()] + args, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, creationflags=CREATE_NO_WINDOW)
        out = []
        for line in p.stdout:
            line = line.rstrip()
            out.append(line)
            self.log(line)
        p.wait()
        return p.returncode, "\n".join(out)

    def detect(self):
        if not os.path.exists(fastboot_exe()):
            self.get_tools()
        _, out = self.fb(["devices"])
        if "fastboot" not in out:
            self.log("ما لقيت حتى هاتف. دخل الهاتف لـ Fastboot (Vol- + Power) وركب الكابل.")
            return
        _, prod = self.fb(["getvar", "product"])
        _, unl = self.fb(["getvar", "unlocked"])
        if "joyeuse" not in prod.lower():
            self.log("تحذير: الهاتف ماشي joyeuse!")
        if "no" in unl.lower():
            self.log("تحذير: الـ bootloader مقفول.")

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
        if not os.path.exists(fastboot_exe()):
            self.get_tools()
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
        # تحقق من وجود الملفات قبل ما نبداو
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
