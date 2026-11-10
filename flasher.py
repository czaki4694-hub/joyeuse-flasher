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
        self.geometry("800x780")
        self.rom_dir = tk.StringVar()
        self.mode = tk.StringVar(value="flash_all.bat")
        self.url = tk.StringVar()
        self.recovery_path = tk.StringVar()
        self.boot_path = tk.StringVar()
        self.reboot_after = tk.BooleanVar(value=True)
        self.info = tk.StringVar(value="اضغط على 'قراءة المعلومات'.")
        self.roms = []
        self.pkgs_all = []
        self.pkg_mode = tk.StringVar(value="system")
        self.pkg_filter = tk.StringVar()
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
        ttk.Entry(row, textvariable=self.url).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row, text="حمل (من اللائحة/الرابط)", command=lambda: self.run_bg(self.download_rom)).pack(side="left", **pad)
        row2 = ttk.Frame(f2)
        row2.pack(fill="x")
        ttk.Entry(row2, textvariable=self.rom_dir).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(row2, text="اختيار فولدر ROM", command=self.pick_dir).pack(side="left", **pad)

        f3 = ttk.LabelFrame(tab_rom, text="3) الفلاش")
        f3.pack(fill="x", **pad)
        ttk.Radiobutton(f3, text="Clean all (كيمسح كلشي)", variable=self.mode, value="flash_all.bat").pack(anchor="w", padx=8)
        ttk.Radiobutton(f3, text="Save user data (كيحافظ على الداتا)", variable=self.mode, value="flash_all_except_storage.bat").pack(anchor="w", padx=8)
        ttk.Button(f3, text="ابدأ الفلاش", command=self.start_flash).pack(anchor="e", **pad)

        # --- تبويب الجهاز ---
        d1 = ttk.LabelFrame(tab_dev, text="معلومات الجهاز")
        d1.pack(fill="x", **pad)
        ttk.Button(d1, text="قراءة المعلومات", command=lambda: self.run_bg(self.device_info)).pack(anchor="w", **pad)
        ttk.Label(d1, textvariable=self.info, justify="left", font=("Consolas", 10)).pack(anchor="w", **pad)

        d2 = ttk.LabelFrame(tab_dev, text="Reboot (كيخدم فـ Fastboot وفـ Android)")
        d2.pack(fill="x", **pad)
        ttk.Button(d2, text="Reboot System", command=lambda: self.run_bg(lambda: self.reboot("system"))).pack(side="left", **pad)
        ttk.Button(d2, text="Reboot Recovery", command=lambda: self.run_bg(lambda: self.reboot("recovery"))).pack(side="left", **pad)
        ttk.Button(d2, text="Reboot Fastboot", command=lambda: self.run_bg(lambda: self.reboot("bootloader"))).pack(side="left", **pad)

        # --- تبويب Recovery / Boot ---
        r1 = ttk.LabelFrame(tab_img, text="فلاش Recovery (TWRP / OrangeFox...)")
        r1.pack(fill="x", **pad)
        rr = ttk.Frame(r1)
        rr.pack(fill="x")
        ttk.Entry(rr, textvariable=self.recovery_path).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(rr, text="اختيار .img", command=lambda: self.pick_img(self.recovery_path)).pack(side="left", **pad)
        ttk.Checkbutton(r1, text="Reboot مباشرة لـ Recovery بعد الفلاش (مهم باش مايرجعش الـ stock recovery)",
                        variable=self.reboot_after).pack(anchor="w", padx=8)
        ttk.Button(r1, text="فلاش Recovery", command=self.start_flash_recovery).pack(anchor="e", **pad)

        b1 = ttk.LabelFrame(tab_img, text="فلاش Boot (boot.img معدل ديال Magisk)")
        b1.pack(fill="x", **pad)
        br = ttk.Frame(b1)
        br.pack(fill="x")
        ttk.Entry(br, textvariable=self.boot_path).pack(side="left", fill="x", expand=True, **pad)
        ttk.Button(br, text="اختيار .img", command=lambda: self.pick_img(self.boot_path)).pack(side="left", **pad)
        ttk.Button(b1, text="فلاش Boot", command=self.start_flash_boot).pack(anchor="e", **pad)

        # --- تبويب التطبيقات ---
        tab_app = ttk.Frame(nb)
        nb.add(tab_app, text="التطبيقات")
        a1 = ttk.LabelFrame(tab_app, text="تطبيقات الهاتف (adb - USB debugging خاصو يكون مفعل)")
        a1.pack(fill="both", expand=True, **pad)
        top = ttk.Frame(a1)
        top.pack(fill="x")
        for text, val in (("النظام", "system"), ("المثبتة", "user"), ("المحذوفة (للاسترجاع)", "removed")):
            ttk.Radiobutton(top, text=text, variable=self.pkg_mode, value=val).pack(side="left", padx=4)
        ttk.Button(top, text="تحميل اللائحة", command=lambda: self.run_bg(self.load_pkgs)).pack(side="left", **pad)
        ttk.Entry(a1, textvariable=self.pkg_filter).pack(fill="x", **pad)
        lf = ttk.Frame(a1)
        lf.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.lb = tk.Listbox(lf, selectmode="extended", height=8, exportselection=False,
                             yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.config(command=self.lb.yview)
        self.pkg_filter.trace_add("write", lambda *a: self.refresh_pkgs())
        btns = ttk.Frame(a1)
        btns.pack(fill="x")
        ttk.Button(btns, text="تعطيل المحدد", command=self.start_debloat).pack(side="left", **pad)
        ttk.Button(btns, text="استرجاع المحدد", command=self.start_restore).pack(side="left", **pad)
        ttk.Button(btns, text="اقتراحات MIUI", command=self.select_suggested).pack(side="left", **pad)
        ttk.Button(btns, text="تصدير APK", command=self.start_export).pack(side="left", **pad)
        ttk.Button(btns, text="تثبيت APK...", command=self.start_install).pack(side="left", **pad)

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", **pad)
        self.txt = scrolledtext.ScrolledText(self, height=12, state="disabled")
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

    # ---------- download helpers ----------
    def download(self, url, dest):
        self.log(f"تحميل: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "JoyeuseFlasher/2.0"})
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

    def ensure_tools(self):
        if not os.path.exists(fastboot_exe()):
            self.get_tools()

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
        root = out
        for dp, _, files in os.walk(out):
            if "flash_all.bat" in files:
                root = dp
                break
        self.rom_dir.set(root)
        self.log(f"ROM واجد: {root}")

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
            self.log("ما لقيت حتى هاتف. دخل الهاتف لـ Fastboot (Vol- + Power) وركب الكابل.")
            return
        prod = self.getvar("product")
        unl = self.getvar("unlocked")
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
        elif self.adb_present():
            lines.append("الوضع: Android (adb)")
            props = [("الموديل", "ro.product.model"), ("الاسم الداخلي", "ro.product.device"),
                     ("Android", "ro.build.version.release"), ("MIUI", "ro.miui.ui.version.name"),
                     ("البناء", "ro.build.version.incremental"), ("Patch", "ro.build.version.security_patch")]
            for label, prop in props:
                _, out = self.adb(["shell", "getprop", prop], quiet=True)
                lines.append(f"{label}: {out.strip() or '?'}")
        else:
            lines.append("ما لقيت حتى هاتف.")
            lines.append("Fastboot: Vol- + Power. Android: فعل USB debugging ووافق على الحاسوب.")
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
