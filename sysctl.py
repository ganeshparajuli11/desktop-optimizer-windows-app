# encoding: utf-8
# SysCtl v3 - Windows System Control Center
# Open Source | github.com/yourname/sysctl
# pip install customtkinter psutil pynvml

import os, gc, threading, time, tempfile, shutil, subprocess, math, json, statistics
import tkinter as tk
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque

import customtkinter as ctk
import psutil

try:
    import ctypes
except ImportError:
    ctypes = None

try:
    import winsound
except ImportError:
    winsound = None

try:
    import winreg
    WINREG_OK = True
except ImportError:
    WINREG_OK = False

try:
    import pynvml
    pynvml.nvmlInit()
    _gh = pynvml.nvmlDeviceGetHandleByIndex(0)
    GPU_NAME = pynvml.nvmlDeviceGetName(_gh)
    GPU_OK = True
except Exception:
    GPU_OK = False
    GPU_NAME = "NVIDIA GPU not detected"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG     = "#0d0d1a"
PANEL  = "#13132a"
CARD   = "#1a1a35"
ROW1   = "#1e1e38"
ROW2   = "#171730"
BLUE   = "#4f8ef7"
GREEN  = "#3ecf82"
RED    = "#e05555"
ORANGE = "#f0a030"
PURPLE = "#9b72f7"
TEAL   = "#2dd4bf"
TEXT   = "#e8e8f0"
MUTED  = "#6060a0"
CAUTION = "#ffb74d"
HIGH_IMPACT = "#ff6b6b"

HISTORY       = 90
MAX_ROWS      = 60
ALERT_COOL    = 60
APP_STATE_DIR_NAME = "SysCtl"
MIN_BACKGROUND_APP_MB = 40
MAX_DAILY_CPU_SAMPLES = 800
STATE_FLUSH_INTERVAL_SEC = 45
CPU_OPT_PRESET_APPS = ["discord", "spotify", "steam", "epic"]
BG_PRESETS = {
    "Work Focus": ["discord", "telegram", "slack", "steam", "epic"],
    "Gaming Focus": ["overlay", "updater", "onedrive", "dropbox", "teams"],
    "Battery Saver": ["onedrive", "dropbox", "steam", "epic", "spotify"],
}


# ══════════════════════════════════════════════
#  Mini graph (canvas-based, no matplotlib)
# ══════════════════════════════════════════════
class MiniGraph(tk.Canvas):
    def __init__(self, parent, color, bg_hex=CARD, max_val=100, height=80, **kw):
        super().__init__(parent, bg=bg_hex, highlightthickness=0, height=height, **kw)
        self.color   = color
        self.max_val = max_val
        self.data    = deque([0.0]*HISTORY, maxlen=HISTORY)
        self.bind("<Configure>", lambda _: self._draw())

    def push(self, value):
        self.data.append(float(min(value, self.max_val)))
        self._draw()

    def _draw(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 4 or H < 4:
            return
        n, pad = len(self.data), 2
        xs = [pad + i*(W-2*pad)/(n-1) for i in range(n)]
        ys = [H - pad - (v/max(self.max_val,1))*(H-2*pad) for v in self.data]
        poly = []
        for x,y in zip(xs,ys): poly += [x,y]
        poly += [xs[-1], H, xs[0], H]
        self.create_polygon(poly, fill=self.color+"28", outline="")
        pts = []
        for x,y in zip(xs,ys): pts += [x,y]
        if len(pts) >= 4:
            self.create_line(pts, fill=self.color, width=2, smooth=True)
        self.create_text(W-6, pad+2, text=f"{self.data[-1]:.0f}",
                         anchor="ne", fill=self.color,
                         font=("Segoe UI", 9, "bold"))


# ══════════════════════════════════════════════
#  Alert manager
# ══════════════════════════════════════════════
class AlertManager:
    def __init__(self):
        self._last = {}

    def check(self, key, value, threshold, title, msg):
        if value < threshold: return
        now = time.time()
        if now - self._last.get(key, 0) < ALERT_COOL: return
        self._last[key] = now
        ps = (f"Add-Type -AssemblyName System.Windows.Forms;"
              f"$n=New-Object System.Windows.Forms.NotifyIcon;"
              f"$n.Icon=[System.Drawing.SystemIcons]::Warning;$n.Visible=$true;"
              f"$n.ShowBalloonTip(6000,'{title}','{msg}',"
              f"[System.Windows.Forms.ToolTipIcon]::Warning);"
              f"Start-Sleep 7;$n.Dispose()")
        threading.Thread(target=lambda: subprocess.run(
            ["powershell","-WindowStyle","Hidden","-Command",ps],
            capture_output=True), daemon=True).start()


# ══════════════════════════════════════════════
#  StandBy fullscreen clock window
# ══════════════════════════════════════════════
class StandByWindow(ctk.CTkToplevel):
    def __init__(self, parent, get_stats_fn):
        super().__init__(parent)
        self.title("SysCtl StandBy")
        self.configure(fg_color="black")
        self.geometry("900x560")
        self._get_stats = get_stats_fn
        self._timer_running = False
        self._timer_start   = None
        self._timer_elapsed = timedelta(0)
        self._fullscreen    = False
        self._alive         = True
        self._build()
        self._tick()
        self.bind("<Escape>", lambda e: self._close())
        self.bind("<F11>",    lambda e: self._toggle_fs())
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        # Top bar
        top = tk.Frame(self, bg="black")
        top.pack(fill="x", padx=30, pady=(20,0))
        self._fs_btn = tk.Button(top, text="[ Fullscreen F11 ]", bg="black",
                                  fg="#333355", relief="flat",
                                  font=("Segoe UI",10), cursor="hand2",
                                  command=self._toggle_fs)
        self._fs_btn.pack(side="right")
        tk.Button(top, text="Close  Esc", bg="black", fg="#333355",
                  relief="flat", font=("Segoe UI",10), cursor="hand2",
                  command=self._close).pack(side="right", padx=10)

        # Main clock
        center = tk.Frame(self, bg="black")
        center.pack(expand=True)

        self._time_lbl = tk.Label(center, text="00:00:00", fg=BLUE, bg="black",
                                   font=("Segoe UI", 96, "bold"))
        self._time_lbl.pack()

        self._date_lbl = tk.Label(center, text="", fg="#4040a0", bg="black",
                                   font=("Segoe UI", 22))
        self._date_lbl.pack(pady=(0,6))

        self._ampm_lbl = tk.Label(center, text="", fg="#303070", bg="black",
                                   font=("Segoe UI", 16))
        self._ampm_lbl.pack()

        # Timer section
        timer_frame = tk.Frame(self, bg="black")
        timer_frame.pack(pady=(10,0))

        tk.Label(timer_frame, text="TIMER", fg="#2a2a60", bg="black",
                 font=("Segoe UI", 11)).pack()
        self._timer_lbl = tk.Label(timer_frame, text="00:00:00",
                                    fg="#2a2a80", bg="black",
                                    font=("Segoe UI", 28, "bold"),
                                    cursor="hand2")
        self._timer_lbl.pack()
        self._timer_lbl.bind("<Button-1>",   self._toggle_timer)
        self._timer_lbl.bind("<Double-Button-1>", self._reset_timer)
        tk.Label(timer_frame, text="click to start/stop   double-click to reset",
                 fg="#1a1a50", bg="black", font=("Segoe UI", 9)).pack()

        # Stats bar
        stats = tk.Frame(self, bg="black")
        stats.pack(side="bottom", fill="x", padx=40, pady=20)

        self._stat_lbls = {}
        for key, label, color in [
            ("cpu",  "CPU",       GREEN),
            ("ram",  "RAM",       BLUE),
            ("gpu",  "GPU Temp",  ORANGE),
            ("vram", "VRAM",      PURPLE),
            ("net",  "Network",   TEAL),
        ]:
            col = tk.Frame(stats, bg="black")
            col.pack(side="left", expand=True)
            tk.Label(col, text=label, fg="#2a2a60", bg="black",
                     font=("Segoe UI", 10)).pack()
            lbl = tk.Label(col, text="--", fg=color, bg="black",
                           font=("Segoe UI", 18, "bold"))
            lbl.pack()
            self._stat_lbls[key] = lbl

    def _tick(self):
        if not self._alive: return
        now = datetime.now()
        self._time_lbl.configure(text=now.strftime("%I:%M:%S").lstrip("0") or "12:00:00")
        self._date_lbl.configure(text=now.strftime("%A, %B %d  %Y"))
        self._ampm_lbl.configure(text=now.strftime("%p"))

        if self._timer_running:
            elapsed = self._timer_elapsed + (datetime.now() - self._timer_start)
        else:
            elapsed = self._timer_elapsed
        h,rem = divmod(int(elapsed.total_seconds()), 3600)
        m,s   = divmod(rem, 60)
        self._timer_lbl.configure(text=f"{h:02d}:{m:02d}:{s:02d}")

        try:
            stats = self._get_stats()
            for key, val in stats.items():
                if key in self._stat_lbls:
                    self._stat_lbls[key].configure(text=val)
        except Exception:
            pass

        self.after(1000, self._tick)

    def _toggle_timer(self, event=None):
        if event and event.type == tk.EventType.ButtonPress:
            if event.num == 1 and not (event.time - getattr(self,'_last_click',0) < 400):
                self._last_click = event.time
                if self._timer_running:
                    self._timer_elapsed += datetime.now() - self._timer_start
                    self._timer_running = False
                    self._timer_lbl.configure(fg=RED)
                else:
                    self._timer_start   = datetime.now()
                    self._timer_running = True
                    self._timer_lbl.configure(fg=GREEN)

    def _reset_timer(self, event=None):
        self._timer_running = False
        self._timer_elapsed = timedelta(0)
        self._timer_start   = None
        self._timer_lbl.configure(text="00:00:00", fg="#2a2a80")

    def _toggle_fs(self):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def _close(self):
        self._alive = False
        self.destroy()


# ══════════════════════════════════════════════
#  Main Application
# ══════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SysCtl v3")
        self.geometry("1200x760")
        self.minsize(980, 640)
        self.configure(fg_color=BG)

        self._alive     = True
        self._sort_var  = ctk.StringVar(value="RAM")
        self._flt_var   = ctk.StringVar()
        self._cpu_mode_var = ctk.StringVar(value="Safe")
        self._home_show_details = ctk.BooleanVar(value=False)
        self._focus_break_sound_var = ctk.BooleanVar(value=False)
        self._focus_with_safe_cpu_var = ctk.BooleanVar(value=False)
        self._net_prev  = None
        self._net_time  = 0
        self._disk_prev = {}
        self._disk_time = 0
        self._last_bg_refresh = 0.0
        self._last_state_flush = 0.0
        self._alerts    = AlertManager()
        self._thr       = {"ram":85.0,"cpu":90.0,"gpu_temp":85.0,"vram":90.0}
        self._profile   = "Normal"
        self._standby_win = None
        self._cpu_samples = deque(maxlen=1200)
        self._last_optimization = None
        self._focus_running = False
        self._focus_remaining = 0
        self._focus_target_minutes = 0
        self._last_assistant_undo = None
        self._safe_system_names = {
            "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
            "lsass.exe", "svchost.exe", "explorer.exe", "winlogon.exe", "dwm.exe", "taskhostw.exe"
        }
        self._friendly_names = {
            "onedrive.exe": "Microsoft OneDrive", "discord.exe": "Discord", "spotify.exe": "Spotify",
            "steam.exe": "Steam", "epicgameslauncher.exe": "Epic Games Launcher",
            "teams.exe": "Microsoft Teams", "telegram.exe": "Telegram", "slack.exe": "Slack",
            "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge", "dropbox.exe": "Dropbox"
        }

        self._state_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_STATE_DIR_NAME
        self._state_file = self._state_dir / "sysctl_state.json"
        self._state = self._default_state()
        self._load_state()
        self._apply_state_vars()
        self._apply_startup_blocklist()

        self._live_stats = {"cpu":"--","ram":"--","gpu":"--","vram":"--","net":"--"}

        self._h_cpu  = deque([0.0]*HISTORY, maxlen=HISTORY)
        self._h_ram  = deque([0.0]*HISTORY, maxlen=HISTORY)
        self._h_gpu  = deque([0.0]*HISTORY, maxlen=HISTORY)
        self._h_netd = deque([0.0]*HISTORY, maxlen=HISTORY)
        self._h_disk = deque([0.0]*HISTORY, maxlen=HISTORY)

        self._build()
        self._rollover_daily_if_needed()
        self._refresh_daily_summary_ui()
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._docker_loop, daemon=True).start()

    # ── BUILD ──────────────────────────────────
    def _build(self):
        self._build_header()
        self._build_stats()
        self._build_tabs()

    # ── STATE / SAFETY ─────────────────────────
    def _default_state(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "settings": {
                "cpu_mode": "Safe",
                "home_show_details": False,
                "focus_break_sound": False,
                "focus_with_safe_cpu": False,
                "bg_whitelist": [],
                "bg_startup_blocklist": [],
                "bg_keep_allowed": [],
            },
            "optimizer_history": [],
            "daily_summary": {
                "date": today,
                "focus_minutes": 0,
                "apps_closed": 0,
                "cpu_samples": [],
                "summary_sentence": "Your PC is running normally.",
            },
        }

    def _apply_state_vars(self):
        settings = self._state.get("settings", {})
        mode = settings.get("cpu_mode", "Safe")
        if mode not in ("Safe", "Balanced", "Aggressive"):
            mode = "Safe"
        self._cpu_mode_var.set(mode)
        self._home_show_details.set(bool(settings.get("home_show_details", False)))
        self._focus_break_sound_var.set(bool(settings.get("focus_break_sound", False)))
        self._focus_with_safe_cpu_var.set(bool(settings.get("focus_with_safe_cpu", False)))

    def _is_admin(self):
        if not ctypes:
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _save_state(self):
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            self._status(f"Could not save settings: {e}")

    def _load_state(self):
        self._state = self._default_state()
        if not self._state_file.exists():
            self._save_state()
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._state.update(loaded)
                self._state["settings"] = {**self._default_state()["settings"], **loaded.get("settings", {})}
                self._state["daily_summary"] = {**self._default_state()["daily_summary"], **loaded.get("daily_summary", {})}
                self._state["optimizer_history"] = loaded.get("optimizer_history", [])
        except Exception:
            try:
                backup = self._state_file.with_suffix(".corrupt.json")
                if self._state_file.exists():
                    shutil.copyfile(self._state_file, backup)
                self._save_state()
            except Exception:
                pass

    def _rollover_daily_if_needed(self):
        daily = self._state.get("daily_summary", {})
        today = datetime.now().strftime("%Y-%m-%d")
        if daily.get("date") == today:
            return
        self._state["daily_summary"] = {
            "date": today,
            "focus_minutes": 0,
            "apps_closed": 0,
            "cpu_samples": [],
            "summary_sentence": "A new day started. Ready when you are.",
        }
        self._save_state()

    def _notify(self, title, message):
        safe_title = str(title).replace("'", "''")
        safe_message = str(message).replace("'", "''")
        ps = (f"Add-Type -AssemblyName System.Windows.Forms;"
              f"$n=New-Object System.Windows.Forms.NotifyIcon;"
              f"$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
              f"$n.ShowBalloonTip(7000,'{safe_title}','{safe_message}',"
              f"[System.Windows.Forms.ToolTipIcon]::Info);Start-Sleep 8;$n.Dispose()")
        threading.Thread(target=lambda: subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps], capture_output=True
        ), daemon=True).start()

    def _risk_meta(self, risk):
        if risk == "Safe":
            return GREEN, "Safe"
        if risk == "Needs Admin":
            return CAUTION, "Needs Admin"
        return HIGH_IMPACT, "Advanced"

    def _show_explain_dialog(self, title, what, expected, risk, on_confirm, needs_admin=False):
        color, risk_text = self._risk_meta(risk)
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("560x340")
        dlg.configure(fg_color=PANEL)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=title, font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=TEXT).pack(pady=(16, 8))
        ctk.CTkLabel(dlg, text=f"What this will do:\n{what}", justify="left",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(dlg, text=f"Expected result:\n{expected}", justify="left",
                     font=ctk.CTkFont(size=12), text_color=MUTED).pack(fill="x", padx=20, pady=6)
        admin_txt = " • Needs Admin" if needs_admin and not self._is_admin() else ""
        ctk.CTkLabel(dlg, text=f"Risk level: {risk_text}{admin_txt}", text_color=color,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(8, 12))
        bar = ctk.CTkFrame(dlg, fg_color="transparent")
        bar.pack(pady=8)
        def confirm():
            dlg.destroy()
            on_confirm()
        ctk.CTkButton(bar, text="Apply", fg_color=color, hover_color=color, command=confirm).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Cancel", command=dlg.destroy).pack(side="left", padx=8)

    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=50)
        h.pack(fill="x"); h.pack_propagate(False)
        ctk.CTkLabel(h, text="  SysCtl v3",
                     font=ctk.CTkFont("Segoe UI",20,"bold"),
                     text_color=BLUE).pack(side="left", padx=14)
        self._prof_lbl = ctk.CTkLabel(h, text="Mode: Normal",
                                       font=ctk.CTkFont(size=12),
                                       text_color=GREEN)
        self._prof_lbl.pack(side="left", padx=18)
        self._clock_lbl = ctk.CTkLabel(h, text="",
                                        font=ctk.CTkFont("Segoe UI",12),
                                        text_color=MUTED)
        self._clock_lbl.pack(side="right", padx=18)

    def _mk_stat(self, parent, title, col, accent):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        f.grid(row=0, column=col, padx=5, pady=5, sticky="ew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11),
                     text_color=accent).pack(pady=(10,1))
        lbl = ctk.CTkLabel(f, text="--",
                            font=ctk.CTkFont("Segoe UI",15,"bold"),
                            text_color=TEXT)
        lbl.pack()
        bar = ctk.CTkProgressBar(f, height=6, corner_radius=3,
                                  fg_color="#1e1e3a", progress_color=accent)
        bar.set(0); bar.pack(fill="x", padx=12, pady=(3,10))
        return lbl, bar

    def _build_stats(self):
        r = ctk.CTkFrame(self, fg_color=BG)
        r.pack(fill="x", padx=14, pady=(8,2))
        for i in range(6): r.columnconfigure(i, weight=1)
        self._s_ram  = self._mk_stat(r,"RAM",     0,BLUE)
        self._s_cpu  = self._mk_stat(r,"CPU",     1,GREEN)
        self._s_gpu  = self._mk_stat(r,"GPU VRAM",2,ORANGE)
        self._s_net  = self._mk_stat(r,"NETWORK", 3,TEAL)
        self._s_disk = self._mk_stat(r,"DISK C:", 4,PURPLE)
        self._s_iops = self._mk_stat(r,"DISK I/O",5,RED)

    def _build_tabs(self):
        self._tabs = ctk.CTkTabview(
            self, fg_color=PANEL,
            segmented_button_fg_color=BG,
            segmented_button_selected_color=BLUE,
            segmented_button_unselected_color=CARD,
            segmented_button_selected_hover_color="#3a7aed")
        self._tabs.pack(fill="both", expand=True, padx=14, pady=(2,12))
        for t in ("Home","CPU Optimizer","Background Apps","Focus Hub","Assistant","Daily Summary",
                  "Dashboard","Processes","Network","Disk I/O","GPU Monitor",
                  "Docker","StandBy","Profiles","Alerts","Startup Apps","Quick Actions"):
            self._tabs.add(t)
        self._build_home()
        self._build_cpu_optimizer()
        self._build_background_apps()
        self._build_focus_hub()
        self._build_assistant()
        self._build_daily_summary()
        self._build_dashboard()
        self._build_procs()
        self._build_network()
        self._build_diskio()
        self._build_gpu()
        self._build_docker()
        self._build_standby_tab()
        self._build_profiles()
        self._build_alerts_tab()
        self._build_startup()
        self._build_actions()

    # ── HOME ───────────────────────────────────
    def _build_home(self):
        tab = self._tabs.tab("Home")
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(top, text="Simple System Health", font=ctk.CTkFont("Segoe UI", 16, "bold"),
                     text_color=BLUE).pack(side="left")
        ctk.CTkCheckBox(top, text="Show details", variable=self._home_show_details,
                        command=self._update_home_cards).pack(side="right")
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=10, pady=8)
        grid.columnconfigure((0, 1, 2), weight=1)
        grid.rowconfigure((0, 1), weight=1)
        self._home_cards = {}
        names = [("CPU", GREEN), ("RAM", BLUE), ("Temperature", ORANGE), ("Battery", PURPLE), ("Network", TEAL)]
        for i, (name, color) in enumerate(names):
            row, col = divmod(i, 3)
            card = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=12)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(card, text=name, text_color=color, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(16, 4))
            state = ctk.CTkLabel(card, text="Good", text_color=GREEN, font=ctk.CTkFont("Segoe UI", 22, "bold"))
            state.pack()
            desc = ctk.CTkLabel(card, text="Healthy and stable", text_color=MUTED, font=ctk.CTkFont(size=12))
            desc.pack(pady=(2, 6))
            details = ctk.CTkLabel(card, text="", text_color=MUTED, font=ctk.CTkFont(size=11))
            details.pack(pady=(0, 12))
            self._home_cards[name] = {"state": state, "desc": desc, "details": details}

    # ── CPU OPTIMIZER ──────────────────────────
    def _build_cpu_optimizer(self):
        tab = self._tabs.tab("CPU Optimizer")
        ctk.CTkLabel(tab, text="Beginner CPU Optimizer", font=ctk.CTkFont("Segoe UI", 20, "bold"),
                     text_color=GREEN).pack(pady=(14, 6))
        mode_row = ctk.CTkFrame(tab, fg_color="transparent")
        mode_row.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(mode_row, text="Mode:", text_color=MUTED).pack(side="left")
        ctk.CTkOptionMenu(mode_row, values=["Safe", "Balanced", "Aggressive"], variable=self._cpu_mode_var,
                          command=lambda _: self._update_cpu_mode_explain()).pack(side="left", padx=8)
        self._cpu_needs_admin = ctk.CTkLabel(mode_row, text="", text_color=CAUTION)
        self._cpu_needs_admin.pack(side="left", padx=8)
        self._cpu_explain = ctk.CTkLabel(tab, text="", justify="left", text_color=MUTED, font=ctk.CTkFont(size=12))
        self._cpu_explain.pack(fill="x", padx=20, pady=(2, 10))
        ctk.CTkButton(tab, text="Optimize CPU Now", width=320, height=56,
                      font=ctk.CTkFont("Segoe UI", 18, "bold"), fg_color=GREEN,
                      command=self._optimize_cpu_now).pack(pady=8)
        ctk.CTkButton(tab, text="Undo Last Optimization", width=220, height=36,
                      fg_color=ORANGE, command=self._undo_last_optimization).pack(pady=(2, 14))
        result = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=12)
        result.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(result, text="Live Result", font=ctk.CTkFont("Segoe UI", 14, "bold"),
                     text_color=BLUE).pack(anchor="w", padx=14, pady=(10, 4))
        self._cpu_before_lbl = ctk.CTkLabel(result, text="CPU before optimization: --", text_color=TEXT)
        self._cpu_before_lbl.pack(anchor="w", padx=14, pady=2)
        self._cpu_after_lbl = ctk.CTkLabel(result, text="CPU after optimization: --", text_color=TEXT)
        self._cpu_after_lbl.pack(anchor="w", padx=14, pady=2)
        self._cpu_avg_lbl = ctk.CTkLabel(result, text="5-minute average comparison: --", text_color=MUTED)
        self._cpu_avg_lbl.pack(anchor="w", padx=14, pady=(2, 12))
        self._cpu_changed_lbl = ctk.CTkLabel(tab, text="No optimization applied yet.", text_color=MUTED)
        self._cpu_changed_lbl.pack(anchor="w", padx=24, pady=6)
        self._update_cpu_mode_explain()

    # ── BACKGROUND APPS ────────────────────────
    def _build_background_apps(self):
        tab = self._tabs.tab("Background Apps")
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(10, 4))
        ctk.CTkLabel(top, text="Background Apps (safe controls)", text_color=BLUE,
                     font=ctk.CTkFont("Segoe UI", 16, "bold")).pack(side="left")
        ctk.CTkButton(top, text="Refresh", width=90, command=self._refresh_background_apps).pack(side="right")
        preset = ctk.CTkFrame(tab, fg_color="transparent")
        preset.pack(fill="x", padx=8, pady=(0, 8))
        for text, cmd in [
            ("Work Focus", lambda: self._apply_bg_preset("Work Focus")),
            ("Gaming Focus", lambda: self._apply_bg_preset("Gaming Focus")),
            ("Battery Saver", lambda: self._apply_bg_preset("Battery Saver")),
        ]:
            ctk.CTkButton(preset, text=text, width=120, command=cmd).pack(side="left", padx=4)
        self._bg_list = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._bg_list.pack(fill="both", expand=True, padx=6, pady=4)
        self._bg_status = ctk.CTkLabel(tab, text="", text_color=MUTED)
        self._bg_status.pack(anchor="w", padx=10, pady=(0, 8))
        self._refresh_background_apps()

    # ── FOCUS HUB ──────────────────────────────
    def _build_focus_hub(self):
        tab = self._tabs.tab("Focus Hub")
        ctk.CTkLabel(tab, text="Focus Mode Hub", font=ctk.CTkFont("Segoe UI", 20, "bold"), text_color=TEAL).pack(pady=(18, 6))
        ctk.CTkLabel(tab, text="Choose a timer and stay focused in a calm full-screen clock mode.",
                     text_color=MUTED).pack()
        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(pady=10)
        ctk.CTkButton(row, text="25 min", width=90, command=lambda: self._start_focus_session(25)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="45 min", width=90, command=lambda: self._start_focus_session(45)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="60 min", width=90, command=lambda: self._start_focus_session(60)).pack(side="left", padx=6)
        ctk.CTkCheckBox(tab, text="Play break reminder sound", variable=self._focus_break_sound_var,
                        command=self._sync_ui_settings).pack(pady=(4, 2))
        ctk.CTkCheckBox(tab, text="Start Focus with Safe CPU Optimize", variable=self._focus_with_safe_cpu_var,
                        command=self._sync_ui_settings).pack(pady=(2, 8))
        self._focus_timer_lbl = ctk.CTkLabel(tab, text="00:00", font=ctk.CTkFont("Segoe UI", 44, "bold"), text_color=TEXT)
        self._focus_timer_lbl.pack(pady=4)
        self._focus_state_lbl = ctk.CTkLabel(tab, text="Ready", text_color=MUTED)
        self._focus_state_lbl.pack(pady=(0, 8))
        ctk.CTkButton(tab, text="Stop Focus Session", fg_color=RED, command=self._stop_focus_session).pack()

    # ── ASSISTANT ──────────────────────────────
    def _build_assistant(self):
        tab = self._tabs.tab("Assistant")
        ctk.CTkLabel(tab, text="Smart Assistant Actions", font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=BLUE).pack(pady=(14, 8))
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=8)
        grid.columnconfigure((0, 1, 2), weight=1)
        actions = [
            ("My PC is slow", "Runs a safe cleanup and optimization sequence.", "Expected result: smoother response.",
             GREEN, self._assistant_pc_slow),
            ("Prepare for meeting", "Starts focus mode and closes distractions safely.", "Expected result: less interruption.",
             TEAL, self._assistant_meeting),
            ("Battery rescue", "Applies safe battery-saving profile.", "Expected result: longer battery life.",
             ORANGE, self._assistant_battery),
        ]
        for i, (title, line, expect, color, cmd) in enumerate(actions):
            card = ctk.CTkFrame(grid, fg_color=CARD, corner_radius=12)
            card.grid(row=0, column=i, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color=color).pack(pady=(16, 4))
            ctk.CTkLabel(card, text=line, text_color=MUTED, justify="center").pack(padx=12)
            ctk.CTkLabel(card, text=expect, text_color=MUTED, justify="center").pack(padx=12, pady=(2, 8))
            ctk.CTkButton(card, text=title, fg_color=color, hover_color=color, command=cmd).pack(padx=14, pady=(0, 14))
        ctk.CTkButton(tab, text="Undo Last Assistant Action", fg_color=ORANGE,
                      command=self._undo_assistant_action).pack(pady=(0, 12))

    # ── DAILY SUMMARY ───────────────────────────
    def _build_daily_summary(self):
        tab = self._tabs.tab("Daily Summary")
        ctk.CTkLabel(tab, text="Daily Summary", font=ctk.CTkFont("Segoe UI", 20, "bold"), text_color=PURPLE).pack(pady=(16, 8))
        self._daily_focus_lbl = ctk.CTkLabel(tab, text="Focus time completed: --", text_color=TEXT)
        self._daily_focus_lbl.pack(anchor="w", padx=20, pady=4)
        self._daily_apps_lbl = ctk.CTkLabel(tab, text="Apps closed by optimizer: --", text_color=TEXT)
        self._daily_apps_lbl.pack(anchor="w", padx=20, pady=4)
        self._daily_cpu_lbl = ctk.CTkLabel(tab, text="CPU stability trend: --", text_color=TEXT)
        self._daily_cpu_lbl.pack(anchor="w", padx=20, pady=4)
        self._daily_sentence_lbl = ctk.CTkLabel(tab, text="", text_color=MUTED, wraplength=800, justify="left")
        self._daily_sentence_lbl.pack(anchor="w", padx=20, pady=(8, 4))

    # ── DASHBOARD ──────────────────────────────
    def _build_dashboard(self):
        tab = self._tabs.tab("Dashboard")
        tab.columnconfigure((0,1), weight=1)
        tab.rowconfigure((0,1), weight=1)
        specs = [
            ("CPU %",        GREEN,  0,0),
            ("RAM %",        BLUE,   0,1),
            ("GPU Load %",   ORANGE, 1,0),
            ("Disk I/O KB/s",RED,    1,1),
        ]
        self._dash_graphs = {}
        for title, color, row, col in specs:
            card = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=12)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(card, text=title,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(anchor="w",padx=14,pady=(12,4))
            g = MiniGraph(card, color=color, bg_hex=CARD, height=130)
            g.pack(fill="both", expand=True, padx=10, pady=(0,12))
            self._dash_graphs[title] = g

    # ── PROCESSES ──────────────────────────────
    def _build_procs(self):
        tab = self._tabs.tab("Processes")
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", padx=4, pady=(8,4))
        ctk.CTkEntry(ctrl, placeholder_text="Filter...",
                     textvariable=self._flt_var, width=190).pack(side="left",padx=(0,6))
        ctk.CTkLabel(ctrl, text="Sort:", text_color=MUTED).pack(side="left")
        ctk.CTkOptionMenu(ctrl, values=["RAM","CPU","Name"],
                          variable=self._sort_var, width=90,
                          command=lambda _: None).pack(side="left",padx=5)
        ctk.CTkButton(ctrl, text="Free RAM", width=100, height=30,
                      fg_color=BLUE, command=self._free_ram).pack(side="right",padx=4)
        hdr = ctk.CTkFrame(tab, fg_color=BG, corner_radius=7, height=28)
        hdr.pack(fill="x",padx=4,pady=(0,2)); hdr.pack_propagate(False)
        for t in ("Process Name","RAM","CPU %","PID","Kill"):
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED).pack(side="left",padx=14,pady=3)
        self._pf = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._pf.pack(fill="both", expand=True, padx=4)
        self._prows = []
        for i in range(MAX_ROWS):
            bg  = ROW1 if i%2==0 else ROW2
            row = ctk.CTkFrame(self._pf, fg_color=bg, corner_radius=7, height=34)
            n   = ctk.CTkLabel(row,text="",width=280,anchor="w",
                               font=ctk.CTkFont(size=12),text_color=TEXT)
            n.pack(side="left",padx=(12,4))
            r   = ctk.CTkLabel(row,text="",width=95,anchor="center",
                               font=ctk.CTkFont(size=12),text_color=TEXT)
            r.pack(side="left",padx=3)
            c   = ctk.CTkLabel(row,text="",width=65,anchor="center",
                               font=ctk.CTkFont(size=12),text_color=MUTED)
            c.pack(side="left",padx=3)
            p   = ctk.CTkLabel(row,text="",width=65,anchor="center",
                               font=ctk.CTkFont(size=11),text_color=MUTED)
            p.pack(side="left",padx=3)
            kb  = ctk.CTkButton(row,text="Kill",width=55,height=24,
                                fg_color=RED,hover_color="#c03030",
                                font=ctk.CTkFont(size=11),command=lambda:None)
            kb.pack(side="right",padx=10)
            self._prows.append({"frame":row,"name":n,"ram":r,"cpu":c,"pid":p,"kill":kb,"vis":False})

    def _render_procs(self, rows):
        for i,wr in enumerate(self._prows):
            if i < len(rows):
                p   = rows[i]
                nm  = p["name"]; nm = (nm[:37]+"..")if len(nm)>39 else nm
                ram = p["ram"]
                rs  = f"{ram/1024:.2f} GB" if ram>1024 else f"{ram:.0f} MB"
                rc  = RED if ram>1500 else ORANGE if ram>500 else TEXT
                wr["name"].configure(text=nm)
                wr["ram"].configure(text=rs,text_color=rc)
                wr["cpu"].configure(text=f"{p['cpu']:.1f}%")
                wr["pid"].configure(text=str(p["pid"]))
                pid = p["pid"]
                wr["kill"].configure(command=lambda pid=pid: self._kill(pid))
                if not wr["vis"]: wr["frame"].pack(fill="x",pady=1); wr["vis"]=True
            else:
                if wr["vis"]: wr["frame"].pack_forget(); wr["vis"]=False

    # ── NETWORK ────────────────────────────────
    def _build_network(self):
        tab = self._tabs.tab("Network")
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x",padx=4,pady=(10,6)); top.columnconfigure((0,1,2,3),weight=1)
        def nc(col,title,accent):
            f = ctk.CTkFrame(top,fg_color=CARD,corner_radius=12)
            f.grid(row=0,column=col,padx=5,sticky="ew")
            ctk.CTkLabel(f,text=title,font=ctk.CTkFont(size=11),text_color=accent).pack(pady=(10,1))
            lbl = ctk.CTkLabel(f,text="--",font=ctk.CTkFont("Segoe UI",17,"bold"),text_color=TEXT)
            lbl.pack(pady=(0,10)); return lbl
        self._net_down  = nc(0,"Download",GREEN)
        self._net_up    = nc(1,"Upload",ORANGE)
        self._net_total = nc(2,"Total Recv",BLUE)
        self._net_sent  = nc(3,"Total Sent",PURPLE)
        gc_card = ctk.CTkFrame(tab, fg_color=CARD, corner_radius=12)
        gc_card.pack(fill="x",padx=4,pady=(0,8))
        ctk.CTkLabel(gc_card,text="Speed History",
                     font=ctk.CTkFont(size=12, weight="bold"),text_color=TEAL).pack(anchor="w",padx=14,pady=(10,2))
        self._net_gd = MiniGraph(gc_card,color=GREEN,bg_hex=CARD,height=60)
        self._net_gd.pack(fill="x",padx=10,pady=(0,2))
        self._net_gu = MiniGraph(gc_card,color=ORANGE,bg_hex=CARD,height=60)
        self._net_gu.pack(fill="x",padx=10,pady=(0,8))
        ctk.CTkLabel(tab,text="Active Connections",
                     font=ctk.CTkFont(size=12, weight="bold"),text_color=TEAL).pack(anchor="w",padx=8,pady=(4,2))
        hdr = ctk.CTkFrame(tab,fg_color=BG,corner_radius=7,height=26)
        hdr.pack(fill="x",padx=4,pady=(0,2)); hdr.pack_propagate(False)
        for t in ("Process","Local","Remote","Status"):
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED).pack(side="left",padx=14,pady=2)
        self._conn_frame = ctk.CTkScrollableFrame(tab,fg_color="transparent",height=140)
        self._conn_frame.pack(fill="x",padx=4)

    # ── DISK I/O ───────────────────────────────
    def _build_diskio(self):
        tab = self._tabs.tab("Disk I/O")

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x",padx=4,pady=(10,6)); top.columnconfigure((0,1,2,3),weight=1)
        def dc(col,title,accent):
            f=ctk.CTkFrame(top,fg_color=CARD,corner_radius=12)
            f.grid(row=0,column=col,padx=5,sticky="ew")
            ctk.CTkLabel(f,text=title,font=ctk.CTkFont(size=11),text_color=accent).pack(pady=(10,1))
            lbl=ctk.CTkLabel(f,text="--",font=ctk.CTkFont("Segoe UI",17,"bold"),text_color=TEXT)
            lbl.pack(pady=(0,10)); return lbl
        self._dk_read  = dc(0,"Read Speed",GREEN)
        self._dk_write = dc(1,"Write Speed",ORANGE)
        self._dk_reads = dc(2,"Total Reads",BLUE)
        self._dk_writes= dc(3,"Total Writes",PURPLE)

        gcard = ctk.CTkFrame(tab,fg_color=CARD,corner_radius=12)
        gcard.pack(fill="x",padx=4,pady=(0,8))
        ctk.CTkLabel(gcard,text="Disk I/O History (KB/s)",
                     font=ctk.CTkFont(size=12, weight="bold"),text_color=RED).pack(anchor="w",padx=14,pady=(10,2))
        self._dk_gr = MiniGraph(gcard,color=GREEN,bg_hex=CARD,height=55)
        self._dk_gr.pack(fill="x",padx=10,pady=(0,2))
        self._dk_gw = MiniGraph(gcard,color=ORANGE,bg_hex=CARD,height=55)
        self._dk_gw.pack(fill="x",padx=10,pady=(0,8))

        ctk.CTkLabel(tab,text="Drives",font=ctk.CTkFont(size=12, weight="bold"),text_color=RED).pack(anchor="w",padx=8,pady=(4,2))
        self._drive_frame = ctk.CTkScrollableFrame(tab,fg_color="transparent",height=90)
        self._drive_frame.pack(fill="x",padx=4,pady=(0,6))

        ctk.CTkLabel(tab,text="Top Disk I/O Processes",
                     font=ctk.CTkFont(size=12, weight="bold"),text_color=RED).pack(anchor="w",padx=8,pady=(4,2))
        hdr = ctk.CTkFrame(tab,fg_color=BG,corner_radius=7,height=26)
        hdr.pack(fill="x",padx=4,pady=(0,2)); hdr.pack_propagate(False)
        for t in ("Process","Read/s","Write/s","Total Read","Total Write"):
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED).pack(side="left",padx=14,pady=2)
        self._diskio_frame = ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._diskio_frame.pack(fill="both",expand=True,padx=4)

    # ── GPU ────────────────────────────────────
    def _build_gpu(self):
        tab = self._tabs.tab("GPU Monitor")
        ctk.CTkLabel(tab,text=GPU_NAME,
                     font=ctk.CTkFont("Segoe UI",16,"bold"),text_color=ORANGE).pack(pady=(14,10))
        if not GPU_OK:
            ctk.CTkLabel(tab,text="Install pynvml: pip install pynvml",text_color=MUTED).pack(); return
        g=ctk.CTkFrame(tab,fg_color="transparent"); g.pack(fill="x",padx=16,pady=4)
        g.columnconfigure((0,1,2,3),weight=1)
        self._gpu_w={}
        for i,(nm,color) in enumerate([("GPU Load",ORANGE),("VRAM",BLUE),("Temp",RED),("Power",GREEN)]):
            card=ctk.CTkFrame(g,fg_color=CARD,corner_radius=12)
            card.grid(row=0,column=i,padx=6,sticky="ew")
            ctk.CTkLabel(card,text=nm,text_color=color,font=ctk.CTkFont(size=12)).pack(pady=(14,4))
            v=ctk.CTkLabel(card,text="--",font=ctk.CTkFont("Segoe UI",28,"bold"),text_color=TEXT); v.pack()
            b=ctk.CTkProgressBar(card,height=8,corner_radius=4,fg_color="#1e1e3a",progress_color=color)
            b.set(0); b.pack(fill="x",padx=16,pady=(4,14))
            self._gpu_w[nm]=(v,b)
        gc=ctk.CTkFrame(tab,fg_color=CARD,corner_radius=12); gc.pack(fill="x",padx=16,pady=(10,4))
        ctk.CTkLabel(gc,text="GPU Load History",font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=ORANGE).pack(anchor="w",padx=14,pady=(10,4))
        self._gpu_graph=MiniGraph(gc,color=ORANGE,bg_hex=CARD,height=100)
        self._gpu_graph.pack(fill="x",padx=10,pady=(0,10))

    # ── DOCKER ─────────────────────────────────
    def _build_docker(self):
        tab = self._tabs.tab("Docker")
        top = ctk.CTkFrame(tab,fg_color="transparent")
        top.pack(fill="x",padx=4,pady=(10,6))
        ctk.CTkLabel(top,text="Running Docker containers",text_color=MUTED).pack(side="left")
        self._docker_status = ctk.CTkLabel(top,text="",text_color=TEAL,font=ctk.CTkFont(size=12))
        self._docker_status.pack(side="left",padx=14)
        ctk.CTkButton(top,text="Refresh",width=90,height=30,
                      command=lambda: threading.Thread(target=self._refresh_docker,daemon=True).start()
                      ).pack(side="right")
        hdr=ctk.CTkFrame(tab,fg_color=BG,corner_radius=7,height=28)
        hdr.pack(fill="x",padx=4,pady=(0,2)); hdr.pack_propagate(False)
        for t in ("Container","Image","CPU %","Memory","Status","Actions"):
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED).pack(side="left",padx=12,pady=3)
        self._docker_frame=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._docker_frame.pack(fill="both",expand=True,padx=4)
        self._docker_info=ctk.CTkLabel(tab,text="",font=ctk.CTkFont(size=11),text_color=MUTED)
        self._docker_info.pack(pady=4)

    # ── STANDBY TAB ────────────────────────────
    def _build_standby_tab(self):
        tab = self._tabs.tab("StandBy")
        ctk.CTkLabel(tab,text="StandBy Clock",
                     font=ctk.CTkFont("Segoe UI",20,"bold"),text_color=BLUE).pack(pady=(30,6))
        ctk.CTkLabel(tab,
                     text="A fullscreen clock for your second monitor.\nShows live CPU, RAM, GPU stats.\nHas a built-in timer. Press F11 for fullscreen, Escape to close.",
                     font=ctk.CTkFont(size=13),text_color=MUTED,justify="center").pack(pady=(0,30))
        ctk.CTkButton(tab,text="Launch StandBy Clock",width=240,height=50,
                      font=ctk.CTkFont("Segoe UI",15,"bold"),
                      fg_color=BLUE,hover_color="#3a7aed",
                      command=self._launch_standby).pack(pady=10)
        ctk.CTkLabel(tab,
                     text="Tip: drag the window to your second monitor, then press F11",
                     font=ctk.CTkFont(size=11),text_color=MUTED).pack(pady=(20,0))

    def _launch_standby(self):
        if self._standby_win and self._standby_win.winfo_exists():
            self._standby_win.lift(); return
        self._standby_win = StandByWindow(self, self._get_standby_stats)

    def _get_standby_stats(self):
        return self._live_stats.copy()

    # ── PROFILES ───────────────────────────────
    def _build_profiles(self):
        tab = self._tabs.tab("Profiles")
        ctk.CTkLabel(tab,text="One-click optimization profiles",
                     font=ctk.CTkFont(size=13),text_color=MUTED).pack(pady=(14,4))
        self._prof_status=ctk.CTkLabel(tab,text="",font=ctk.CTkFont(size=13),text_color=GREEN)
        self._prof_status.pack(pady=(0,10))
        g=ctk.CTkFrame(tab,fg_color="transparent"); g.pack(fill="both",expand=True,padx=20,pady=4)
        g.columnconfigure((0,1),weight=1)
        profiles=[
            ("Gaming Mode",   ORANGE,[
                "Max performance power plan",
                "Kill Discord, Spotify, OneDrive",
                "GPU priority = 8 (maximum)",
                "Disable background recording",
                "Free RAM before session",
            ],self._profile_gaming,0,0),
            ("Dev Mode",      BLUE,[
                "Balanced power plan",
                "Preserve Docker + Node.js",
                "Clean npm + pip caches",
                "Optimized for multi-tasking",
                "Keep terminal tools running",
            ],self._profile_dev,0,1),
            ("Battery Saver", GREEN,[
                "Power Saver plan",
                "Kill Steam + Epic Games",
                "Disable telemetry services",
                "Reduce background polling",
                "Pause Windows Update",
            ],self._profile_battery,1,0),
            ("Normal Mode",   PURPLE,[
                "Balanced power plan",
                "Restore default settings",
                "Re-enable standard services",
                "Reset GPU priority",
                "GameDVR restored",
            ],self._profile_normal,1,1),
        ]
        for name,color,feats,cmd,row,col in profiles:
            card=ctk.CTkFrame(g,fg_color=CARD,corner_radius=14)
            card.grid(row=row,column=col,padx=10,pady=10,sticky="nsew")
            ctk.CTkLabel(card,text=name,font=ctk.CTkFont("Segoe UI",14,"bold"),
                         text_color=color).pack(pady=(16,6))
            for f in feats:
                ctk.CTkLabel(card,text="  + "+f,font=ctk.CTkFont(size=11),
                             text_color=MUTED,anchor="w").pack(anchor="w",padx=20)
            ctk.CTkButton(card,text="Activate "+name,height=34,fg_color=color,
                          hover_color=color,command=cmd).pack(padx=20,pady=(10,16))
        for r in range(2): g.rowconfigure(r,weight=1)

    # ── ALERTS ─────────────────────────────────
    def _build_alerts_tab(self):
        tab = self._tabs.tab("Alerts")
        ctk.CTkLabel(tab,text="Windows notifications when thresholds are exceeded",
                     font=ctk.CTkFont(size=13),text_color=MUTED).pack(pady=(16,20))
        self._thr_vars={}
        for label,key,color,mn,mx,unit in [
            ("RAM Usage %",      "ram",      BLUE,  0,100,"%"),
            ("CPU Usage %",      "cpu",      GREEN, 0,100,"%"),
            ("GPU Temperature",  "gpu_temp", RED,  40,110,"C"),
            ("VRAM Usage %",     "vram",     ORANGE,0,100,"%"),
        ]:
            row=ctk.CTkFrame(tab,fg_color=CARD,corner_radius=10)
            row.pack(fill="x",padx=40,pady=6)
            ctk.CTkLabel(row,text=label,width=180,anchor="w",
                         font=ctk.CTkFont(size=13),text_color=color).pack(side="left",padx=20,pady=14)
            var=ctk.DoubleVar(value=self._thr[key]); self._thr_vars[key]=var
            vl=ctk.CTkLabel(row,text=f"{self._thr[key]:.0f}{unit}",
                             font=ctk.CTkFont(size=13, weight="bold"),text_color=TEXT,width=50)
            vl.pack(side="right",padx=20)
            sl=ctk.CTkSlider(row,from_=mn,to=mx,variable=var,width=280,
                              progress_color=color,button_color=color)
            sl.pack(side="right",padx=10)
            sl.configure(command=lambda v,l=vl,k=key,u=unit: (
                self._thr.__setitem__(k,v), l.configure(text=f"{v:.0f}{u}")))
        ctk.CTkLabel(tab,text="Alerts fire at most once per minute per metric",
                     font=ctk.CTkFont(size=11),text_color=MUTED).pack(pady=(20,4))

    # ── STARTUP ────────────────────────────────
    def _build_startup(self):
        tab = self._tabs.tab("Startup Apps")
        top=ctk.CTkFrame(tab,fg_color="transparent"); top.pack(fill="x",padx=4,pady=(10,6))
        ctk.CTkLabel(top,text="Apps that auto-launch on boot",text_color=MUTED).pack(side="left")
        ctk.CTkButton(top,text="Refresh",width=90,height=30,command=self._load_startup).pack(side="right")
        hdr=ctk.CTkFrame(tab,fg_color=BG,corner_radius=7,height=26)
        hdr.pack(fill="x",padx=4,pady=(0,2)); hdr.pack_propagate(False)
        for t in ("Name","Path","Source","Action"):
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=MUTED).pack(side="left",padx=18,pady=2)
        self._sf=ctk.CTkScrollableFrame(tab,fg_color="transparent")
        self._sf.pack(fill="both",expand=True,padx=4)
        self._load_startup()

    def _load_startup(self):
        for w in self._sf.winfo_children(): w.destroy()
        items=[]
        if WINREG_OK:
            for hive,path,src in [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run","HKCU"),
                (winreg.HKEY_LOCAL_MACHINE,r"Software\Microsoft\Windows\CurrentVersion\Run","HKLM"),
            ]:
                try:
                    k=winreg.OpenKey(hive,path); i=0
                    while True:
                        try:
                            n,v,_=winreg.EnumValue(k,i)
                            items.append({"name":n,"val":v,"src":src,"hive":hive,"path":path,"file":None}); i+=1
                        except OSError: break
                    winreg.CloseKey(k)
                except Exception: pass
        folder=Path(os.environ.get("APPDATA",""))/"Microsoft/Windows/Start Menu/Programs/Startup"
        if folder.exists():
            for f in folder.iterdir():
                if f.name!="desktop.ini":
                    items.append({"name":f.name,"val":str(f),"src":"Folder","hive":None,"path":None,"file":f})
        if not items:
            ctk.CTkLabel(self._sf,text="No startup apps found.",text_color=MUTED).pack(pady=30); return
        for i,it in enumerate(items):
            bg=ROW1 if i%2==0 else ROW2
            row=ctk.CTkFrame(self._sf,fg_color=bg,corner_radius=7); row.pack(fill="x",pady=1)
            sc=BLUE if it["src"]=="HKCU" else ORANGE if it["src"]=="HKLM" else GREEN
            ctk.CTkLabel(row,text=it["name"][:36],width=220,anchor="w",
                         font=ctk.CTkFont(size=12),text_color=TEXT).pack(side="left",padx=(14,4),pady=10)
            ctk.CTkLabel(row,text=it["val"][:48],width=290,anchor="w",
                         font=ctk.CTkFont(size=10),text_color=MUTED).pack(side="left",padx=4)
            ctk.CTkLabel(row,text=it["src"],width=90,anchor="center",
                         font=ctk.CTkFont(size=11),text_color=sc).pack(side="left",padx=8)
            item=it
            ctk.CTkButton(row,text="Remove",width=76,height=26,fg_color=RED,
                          hover_color="#c03030",font=ctk.CTkFont(size=11),
                          command=lambda item=item: self._rm_startup(item)).pack(side="right",padx=12,pady=8)

    def _rm_startup(self,it):
        try:
            if it["file"]: it["file"].unlink()
            elif WINREG_OK and it["hive"] and it["path"]:
                k=winreg.OpenKey(it["hive"],it["path"],0,winreg.KEY_ALL_ACCESS)
                winreg.DeleteValue(k,it["name"]); winreg.CloseKey(k)
            self._status(f"Removed: {it['name']}"); self._load_startup()
        except PermissionError: self._status("Permission denied - run as Administrator")
        except Exception as e: self._status(f"Error: {e}")

    # ── QUICK ACTIONS ──────────────────────────
    def _build_actions(self):
        tab=self._tabs.tab("Quick Actions")
        self._status_lbl=ctk.CTkLabel(tab,text="Ready",
                                       font=ctk.CTkFont(size=13),text_color=GREEN)
        self._status_lbl.pack(pady=(14,8))
        g=ctk.CTkFrame(tab,fg_color="transparent"); g.pack(fill="both",expand=True,padx=20,pady=4)
        g.columnconfigure((0,1,2),weight=1)
        for lbl,desc,color,cmd,row,col in [
            ("Free RAM",         "Trim working sets\n+ GC collect",        BLUE,   self._free_ram,  0,0),
            ("Clean Temp",       "Delete %TEMP%\n+ Windows Temp",          GREEN,  self._clean_temp,0,1),
            ("Flush DNS",        "Clear DNS cache",                         PURPLE, self._flush_dns, 0,2),
            ("Boost Power Plan", "High Performance\npower plan",            ORANGE, self._boost_perf,1,0),
            ("Kill RAM Hogs",    "Kill processes\nover 500 MB",             RED,    self._kill_hogs, 1,1),
            ("Task Manager",     "Open startup\nmanager",                   MUTED,  self._open_tm,   1,2),
        ]:
            card=ctk.CTkFrame(g,fg_color=CARD,corner_radius=12)
            card.grid(row=row,column=col,padx=8,pady=8,sticky="nsew")
            ctk.CTkLabel(card,text=lbl,font=ctk.CTkFont("Segoe UI",13,"bold"),
                         text_color=color).pack(pady=(16,4))
            ctk.CTkLabel(card,text=desc,font=ctk.CTkFont(size=11),text_color=MUTED).pack(pady=(0,8))
            ctk.CTkButton(card,text=lbl,height=34,fg_color=color,hover_color=color,
                          command=cmd).pack(padx=16,pady=(0,16))
        for r in range(2): g.rowconfigure(r,weight=1)

    # ── NEW BEGINNER FEATURES ──────────────────
    def _sync_ui_settings(self):
        settings = self._state.setdefault("settings", {})
        settings["cpu_mode"] = self._cpu_mode_var.get()
        settings["home_show_details"] = bool(self._home_show_details.get())
        settings["focus_break_sound"] = bool(self._focus_break_sound_var.get())
        settings["focus_with_safe_cpu"] = bool(self._focus_with_safe_cpu_var.get())
        self._save_state()

    def _status_from_pct(self, value, warn=70, critical=90):
        if value >= critical:
            return "Critical", RED
        if value >= warn:
            return "Warning", ORANGE
        return "Good", GREEN

    def _update_home_cards(self):
        self._sync_ui_settings()
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        cpu_state, cpu_col = self._status_from_pct(cpu)
        ram_state, ram_col = self._status_from_pct(vm.percent)
        temp_value = 0.0
        try:
            if GPU_OK:
                h = pynvml.nvmlDeviceGetHandleByIndex(0)
                temp_value = float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
            else:
                temp_value = 35.0
        except Exception:
            temp_value = 0.0
        temp_state, temp_col = self._status_from_pct(temp_value, warn=70, critical=85)
        bat = psutil.sensors_battery()
        bat_pct = float(bat.percent) if bat else 100.0
        bat_state, bat_col = self._status_from_pct(100 - bat_pct, warn=30, critical=60)
        net_kb = self._h_netd[-1] if self._h_netd else 0.0
        net_state, net_col = ("Good", GREEN) if net_kb > 20 else ("Warning", ORANGE)
        data = {
            "CPU": (cpu_state, cpu_col, "Processor load is stable" if cpu_state == "Good" else "Processor is busy",
                    f"Current usage: {cpu:.0f}%"),
            "RAM": (ram_state, ram_col, "Memory pressure is low" if ram_state == "Good" else "Memory usage is high",
                    f"Current usage: {vm.percent:.0f}% ({vm.used/1e9:.1f} GB used)"),
            "Temperature": (temp_state, temp_col, "Thermals are safe" if temp_state == "Good" else "System is warming up",
                            f"Measured temperature: {temp_value:.0f}°C" if temp_value else "Temperature not available"),
            "Battery": (bat_state if bat else "Good", bat_col if bat else GREEN,
                        "Battery level is comfortable" if bat and bat_state == "Good" else "Enable saver for longer runtime",
                        f"Battery: {bat_pct:.0f}%" if bat else "Battery not available"),
            "Network": (net_state, net_col, "Network activity looks normal", f"Download traffic: {net_kb:.0f} KB/s"),
        }
        for key, vals in data.items():
            if key not in self._home_cards:
                continue
            st, col, desc, details = vals
            self._home_cards[key]["state"].configure(text=st, text_color=col)
            self._home_cards[key]["desc"].configure(text=desc)
            self._home_cards[key]["details"].configure(text=details if self._home_show_details.get() else "")

    def _update_cpu_mode_explain(self):
        mode = self._cpu_mode_var.get()
        explain = {
            "Safe": "Safe: light cleanup and memory trim. Best for beginners and everyday use.",
            "Balanced": "Balanced: Safe mode plus balanced power plan tuning for smoother performance.",
            "Aggressive": "Aggressive: stronger tuning and app cleanup. Higher impact and may need admin rights.",
        }
        needs_admin = mode in ("Balanced", "Aggressive") and not self._is_admin()
        self._cpu_explain.configure(text=explain.get(mode, explain["Safe"]))
        self._cpu_needs_admin.configure(text="Needs Admin" if needs_admin else "")
        self._sync_ui_settings()

    def _cpu_avg_last_minutes(self, minutes=5):
        now = time.time()
        vals = [v for ts, v in self._cpu_samples if (now - ts) <= minutes * 60]
        if not vals:
            vals = list(self._h_cpu)[-20:]
        return (sum(vals) / max(len(vals), 1)) if vals else 0.0

    def _run_cpu_optimize(self, mode, initiated_by_focus=False):
        before = psutil.cpu_percent(interval=0.3)
        avg_before = self._cpu_avg_last_minutes(5)
        changed = []
        undo = {"mode": mode, "prev_power_guid": self._get_active_power_guid()}
        try:
            gc.collect()
            changed.append("Freed memory garbage")
            if mode in ("Balanced", "Aggressive"):
                self._set_power("Balanced" if mode == "Balanced" else "High performance")
                changed.append("Adjusted power plan for performance")
            if mode == "Aggressive":
                closed = self._stop_background_group(CPU_OPT_PRESET_APPS, silent=True)
                if closed:
                    changed.append(f"Closed {closed} heavy background app(s)")
                    self._add_daily_apps_closed(closed)
        except Exception as e:
            self._status(f"Optimization fallback used: {e}")
        after = psutil.cpu_percent(interval=0.4)
        avg_after = self._cpu_avg_last_minutes(5)
        self._last_optimization = undo
        hist = self._state.setdefault("optimizer_history", [])
        hist.append({
            "time": datetime.now().isoformat(),
            "mode": mode,
            "before_cpu": before,
            "after_cpu": after,
            "before_avg_5m": avg_before,
            "after_avg_5m": avg_after,
            "changes": changed,
        })
        self._state["optimizer_history"] = hist[-40:]
        self._save_state()
        msg = ", ".join(changed) if changed else "No risky changes were applied."
        self.after(0, lambda: (
            self._cpu_before_lbl.configure(text=f"CPU before optimization: {before:.0f}%"),
            self._cpu_after_lbl.configure(text=f"CPU after optimization: {after:.0f}%"),
            self._cpu_avg_lbl.configure(text=f"5-minute average comparison: {avg_before:.1f}% → {avg_after:.1f}%"),
            self._cpu_changed_lbl.configure(text=f"What changed: {msg}" if not initiated_by_focus else f"Focus start optimize: {msg}")
        ))

    def _optimize_cpu_now(self):
        mode = self._cpu_mode_var.get()
        risk = "Safe" if mode == "Safe" else ("Needs Admin" if mode == "Balanced" else "Advanced")
        needs_admin = mode in ("Balanced", "Aggressive")
        what = f"Apply {mode} CPU optimization with beginner-safe defaults."
        expected = "Lower short CPU spikes and better responsiveness."
        def run_confirmed():
            threading.Thread(target=lambda: self._run_cpu_optimize(mode), daemon=True).start()
        self._show_explain_dialog("CPU Optimizer", what, expected, risk, run_confirmed, needs_admin=needs_admin)

    def _get_active_power_guid(self):
        try:
            out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=4).stdout
            for token in out.split():
                if "-" in token and len(token) > 20:
                    return token.strip("()")
        except Exception:
            pass
        return None

    def _set_power_guid(self, guid):
        if not guid:
            return
        self._ps(f"powercfg /setactive {guid}")

    def _undo_last_optimization(self):
        if not self._last_optimization:
            self._status("Nothing to undo yet.")
            return
        prev = self._last_optimization.get("prev_power_guid")
        def run():
            self._set_power_guid(prev)
            self.after(0, lambda: self._cpu_changed_lbl.configure(text="Undo complete: restored previous power settings where possible."))
        threading.Thread(target=run, daemon=True).start()

    def _friendly_name(self, proc_name):
        nm = (proc_name or "").lower()
        return self._friendly_names.get(nm, (proc_name or "Unknown App"))

    def _is_system_critical(self, proc_name):
        return (proc_name or "").lower() in self._safe_system_names

    def _get_background_candidates(self):
        items = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                nm = (p.info["name"] or "").strip()
                if not nm or self._is_system_critical(nm):
                    continue
                rss = (p.info["memory_info"].rss / 1048576.0) if p.info.get("memory_info") else 0.0
                if rss < MIN_BACKGROUND_APP_MB and "update" not in nm.lower() and "launcher" not in nm.lower():
                    continue
                items.append({"pid": p.info["pid"], "name": nm, "ram": rss})
            except Exception:
                pass
        items.sort(key=lambda x: x["ram"], reverse=True)
        return items[:40]

    def _refresh_background_apps(self):
        if not hasattr(self, "_bg_list"):
            return
        for w in self._bg_list.winfo_children():
            w.destroy()
        settings = self._state.setdefault("settings", {})
        whitelist = set(settings.get("bg_whitelist", []))
        apps = self._get_background_candidates()
        if not apps:
            ctk.CTkLabel(self._bg_list, text="No heavy background apps found.", text_color=MUTED).pack(pady=20)
            return
        for i, app in enumerate(apps):
            bg = ROW1 if i % 2 == 0 else ROW2
            row = ctk.CTkFrame(self._bg_list, fg_color=bg, corner_radius=7)
            row.pack(fill="x", pady=2)
            name = app["name"]
            friendly = self._friendly_name(name)
            ctk.CTkLabel(row, text=friendly[:28], width=220, anchor="w", text_color=TEXT).pack(side="left", padx=(10, 2), pady=10)
            ctk.CTkLabel(row, text=f"{app['ram']:.0f} MB", width=70, text_color=MUTED).pack(side="left")
            if name.lower() in whitelist:
                ctk.CTkLabel(row, text="Always allowed", text_color=GREEN, width=100).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Stop now", width=70, height=26, fg_color=RED,
                          command=lambda a=app: self._stop_background_app(a)).pack(side="right", padx=4)
            ctk.CTkButton(row, text="Stop on startup", width=110, height=26, fg_color=ORANGE,
                          command=lambda n=name: self._mark_stop_on_startup(n)).pack(side="right", padx=4)
            ctk.CTkButton(row, text="Keep always allowed", width=130, height=26, fg_color=GREEN,
                          command=lambda n=name: self._add_whitelist(n)).pack(side="right", padx=4)
        self._bg_status.configure(text=f"Showing {len(apps)} background apps. System-critical apps are always protected.")

    def _stop_background_app(self, app):
        nm = app.get("name", "")
        if self._is_system_critical(nm):
            self._bg_status.configure(text=f"Safe fallback: {nm} is protected.")
            return
        def do_stop():
            try:
                psutil.Process(app["pid"]).terminate()
                self._add_daily_apps_closed(1)
                self._bg_status.configure(text=f"Stopped {self._friendly_name(nm)} safely.")
            except psutil.AccessDenied:
                self._bg_status.configure(text=f"Needs Admin to stop {self._friendly_name(nm)}.")
            except Exception:
                self._bg_status.configure(text=f"Safe fallback: could not stop {self._friendly_name(nm)}.")
            self.after(200, self._refresh_background_apps)
        self._show_explain_dialog(
            "Stop Background App",
            f"Stop {self._friendly_name(nm)} now.",
            "Lower background load and free memory.",
            "Needs Admin",
            do_stop,
            needs_admin=True,
        )

    def _add_whitelist(self, proc_name):
        settings = self._state.setdefault("settings", {})
        wl = set(settings.get("bg_whitelist", []))
        wl.add(proc_name.lower())
        settings["bg_whitelist"] = sorted(wl)
        self._save_state()
        self._refresh_background_apps()
        self._bg_status.configure(text=f"{self._friendly_name(proc_name)} added to always allowed list.")

    def _mark_stop_on_startup(self, proc_name):
        settings = self._state.setdefault("settings", {})
        blocked = set(settings.get("bg_startup_blocklist", []))
        blocked.add(proc_name.lower())
        settings["bg_startup_blocklist"] = sorted(blocked)
        self._save_state()
        self._apply_startup_blocklist()
        self._bg_status.configure(text=f"{self._friendly_name(proc_name)} will be blocked on startup where possible.")

    def _apply_startup_blocklist(self):
        blocked = set(self._state.get("settings", {}).get("bg_startup_blocklist", []))
        if not blocked:
            return
        try:
            folder = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
            if folder.exists():
                for f in folder.iterdir():
                    if any(b in f.name.lower() for b in blocked):
                        try:
                            f.unlink()
                        except Exception:
                            pass
            if WINREG_OK:
                for hive, path in [
                    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                ]:
                    try:
                        k = winreg.OpenKey(hive, path, 0, winreg.KEY_ALL_ACCESS)
                    except Exception:
                        continue
                    i, to_delete = 0, []
                    while True:
                        try:
                            n, v, _ = winreg.EnumValue(k, i)
                            if any(b in n.lower() or b in str(v).lower() for b in blocked):
                                to_delete.append(n)
                            i += 1
                        except OSError:
                            break
                    for n in to_delete:
                        try:
                            winreg.DeleteValue(k, n)
                        except Exception:
                            pass
                    try:
                        winreg.CloseKey(k)
                    except Exception:
                        pass
        except Exception:
            pass

    def _stop_background_group(self, keywords, silent=False):
        count = 0
        wl = set(self._state.get("settings", {}).get("bg_whitelist", []))
        for p in psutil.process_iter(["pid", "name"]):
            try:
                nm = (p.info["name"] or "").lower()
                if nm in wl or self._is_system_critical(nm):
                    continue
                if any(k in nm for k in keywords):
                    p.terminate()
                    count += 1
            except Exception:
                pass
        if not silent and hasattr(self, "_bg_status"):
            self._bg_status.configure(text=f"Preset complete: closed {count} app(s).")
        return count

    def _apply_bg_preset(self, preset):
        keys = BG_PRESETS.get(preset, [])
        def run():
            closed = self._stop_background_group(keys)
            self._add_daily_apps_closed(closed)
            self._refresh_background_apps()
        self._show_explain_dialog(
            f"{preset} Preset",
            f"Close common distraction/background apps for {preset.lower()}.",
            "Lower background load and improve focus/battery.",
            "Safe",
            run,
            needs_admin=False,
        )

    def _start_focus_session(self, minutes):
        if self._focus_running:
            self._status("Focus session already running.")
            return
        self._focus_target_minutes = minutes
        self._focus_remaining = minutes * 60
        self._focus_running = True
        self._focus_state_lbl.configure(text=f"Focus active for {minutes} minutes", text_color=GREEN)
        if self._focus_with_safe_cpu_var.get():
            threading.Thread(target=lambda: self._run_cpu_optimize("Safe", initiated_by_focus=True), daemon=True).start()
        self._launch_standby()
        self._tick_focus()
        self._sync_ui_settings()

    def _tick_focus(self):
        if not self._focus_running:
            return
        mins, secs = divmod(max(self._focus_remaining, 0), 60)
        self._focus_timer_lbl.configure(text=f"{mins:02d}:{secs:02d}")
        if self._focus_remaining <= 0:
            self._focus_running = False
            self._focus_state_lbl.configure(text="Focus session complete", text_color=TEAL)
            self._notify("SysCtl Focus", "Focus session complete. Time for a short break.")
            if self._focus_break_sound_var.get() and winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass
            self._add_daily_focus_minutes(self._focus_target_minutes)
            return
        self._focus_remaining -= 1
        self.after(1000, self._tick_focus)

    def _stop_focus_session(self):
        self._focus_running = False
        self._focus_timer_lbl.configure(text="00:00")
        self._focus_state_lbl.configure(text="Stopped", text_color=MUTED)

    def _assistant_pc_slow(self):
        def run():
            threading.Thread(target=lambda: self._run_cpu_optimize("Safe"), daemon=True).start()
            threading.Thread(target=self._free_ram, daemon=True).start()
            self._last_assistant_undo = self._undo_last_optimization
            self._status("Assistant: ran safe speed-up sequence.")
        self._show_explain_dialog(
            "My PC is slow",
            "Run safe cleanup and light CPU optimization only.",
            "PC should feel smoother in normal tasks.",
            "Safe",
            run,
            needs_admin=False,
        )

    def _assistant_meeting(self):
        def run():
            closed = self._stop_background_group(BG_PRESETS.get("Work Focus", []), silent=True)
            self._add_daily_apps_closed(closed)
            self._refresh_background_apps()
            self._start_focus_session(45)
            self._last_assistant_undo = self._stop_focus_session
        self._show_explain_dialog(
            "Prepare for meeting",
            "Start focus mode and reduce distractions safely.",
            "Cleaner desktop and fewer interruption apps.",
            "Safe",
            run,
            needs_admin=False,
        )

    def _assistant_battery(self):
        prev = self._get_active_power_guid()
        def run():
            self._set_power("Power saver")
            closed = self._stop_background_group(["steam", "epic", "onedrive", "dropbox"], silent=True)
            self._add_daily_apps_closed(closed)
            self._status("Assistant: battery rescue applied.")
            self._last_assistant_undo = lambda: self._set_power_guid(prev)
        self._show_explain_dialog(
            "Battery rescue",
            "Apply a safe battery-saving profile and close heavy sync tools.",
            "Longer battery runtime with minimal side effects.",
            "Safe",
            run,
            needs_admin=False,
        )

    def _undo_assistant_action(self):
        if self._last_assistant_undo:
            try:
                self._last_assistant_undo()
                self._status("Assistant undo completed where possible.")
            except Exception as e:
                self._status(f"Undo fallback used: {e}")
        else:
            self._status("No assistant action to undo.")

    def _add_daily_focus_minutes(self, minutes):
        self._rollover_daily_if_needed()
        daily = self._state.setdefault("daily_summary", {})
        daily["focus_minutes"] = int(daily.get("focus_minutes", 0)) + int(minutes)
        self._recompute_daily_sentence()
        self._save_state()
        self._refresh_daily_summary_ui()

    def _add_daily_apps_closed(self, count):
        self._rollover_daily_if_needed()
        daily = self._state.setdefault("daily_summary", {})
        daily["apps_closed"] = int(daily.get("apps_closed", 0)) + int(max(count, 0))
        self._recompute_daily_sentence()
        self._save_state()
        self._refresh_daily_summary_ui()

    def _record_daily_cpu(self, value):
        self._rollover_daily_if_needed()
        daily = self._state.setdefault("daily_summary", {})
        samples = daily.setdefault("cpu_samples", [])
        samples.append(float(value))
        if len(samples) > MAX_DAILY_CPU_SAMPLES:
            samples[:] = samples[-MAX_DAILY_CPU_SAMPLES:]
        self._recompute_daily_sentence()

    def _cpu_stability_text(self):
        samples = self._state.get("daily_summary", {}).get("cpu_samples", [])
        if len(samples) < 8:
            return "Collecting data"
        stdev = statistics.pstdev(samples)
        if stdev < 8:
            return "Stable"
        if stdev < 15:
            return "Moderate"
        return "Spiky"

    def _recompute_daily_sentence(self):
        daily = self._state.setdefault("daily_summary", {})
        focus = int(daily.get("focus_minutes", 0))
        apps = int(daily.get("apps_closed", 0))
        stability = self._cpu_stability_text()
        if focus >= 60 and stability == "Stable":
            sentence = "Great day: solid focus time and very steady system performance."
        elif apps > 10:
            sentence = "Nice cleanup: many background apps were closed for a lighter system."
        elif stability == "Spiky":
            sentence = "CPU activity was uneven today; use Safe optimize when things feel slow."
        else:
            sentence = "System health is on track with safe optimizations."
        daily["summary_sentence"] = sentence

    def _refresh_daily_summary_ui(self):
        if not hasattr(self, "_daily_focus_lbl"):
            return
        daily = self._state.get("daily_summary", {})
        self._daily_focus_lbl.configure(text=f"Focus time completed: {int(daily.get('focus_minutes', 0))} minutes")
        self._daily_apps_lbl.configure(text=f"Apps closed by optimizer: {int(daily.get('apps_closed', 0))}")
        self._daily_cpu_lbl.configure(text=f"CPU stability trend: {self._cpu_stability_text()}")
        self._daily_sentence_lbl.configure(text=daily.get("summary_sentence", "System health is on track."))

    # ── REFRESH LOOP ───────────────────────────
    def _loop(self):
        # Main refresh loop — never blocked by Docker
        while self._alive:
            try:
                self._refresh_stats()
                self._refresh_procs()
                self._refresh_network()
                self._refresh_diskio()
                if GPU_OK: self._refresh_gpu()
                now = time.time()
                if now - self._last_bg_refresh > 10:
                    self._last_bg_refresh = now
                    self.after(0, self._refresh_background_apps)
                if now - self._last_state_flush > STATE_FLUSH_INTERVAL_SEC:
                    self._last_state_flush = now
                    self._save_state()
                self.after(0, self._update_home_cards)
                self.after(0, self._refresh_daily_summary_ui)
            except Exception:
                pass
            time.sleep(1.5)

    def _docker_loop(self):
        # Docker runs in its own thread so it can never lag the main UI
        while self._alive:
            try:
                self._refresh_docker()
            except Exception:
                pass
            time.sleep(8)  # Docker refresh every 8s — docker stats is slow

    def _refresh_stats(self):
        vm   = psutil.virtual_memory()
        cpu  = psutil.cpu_percent(interval=None)
        disk = psutil.disk_usage("C:\\")
        u_gb = vm.used/1e9; t_gb = vm.total/1e9
        f_gb = disk.free/1e9
        clk  = datetime.now().strftime("%H:%M:%S   %a %d %b %Y")
        self._h_cpu.append(cpu); self._h_ram.append(vm.percent)
        self._cpu_samples.append((time.time(), float(cpu)))
        self._record_daily_cpu(cpu)
        self._live_stats["cpu"] = f"{cpu:.0f}%"
        self._live_stats["ram"] = f"{vm.percent:.0f}%"
        self._alerts.check("ram",vm.percent,self._thr["ram"],"SysCtl - RAM",f"RAM is {vm.percent:.0f}%")
        self._alerts.check("cpu",cpu,self._thr["cpu"],"SysCtl - CPU",f"CPU is {cpu:.0f}%")
        def apply():
            self._s_ram[0].configure(text=f"{u_gb:.1f}/{t_gb:.0f} GB"); self._s_ram[1].set(vm.percent/100)
            cc=RED if cpu>80 else ORANGE if cpu>50 else GREEN
            self._s_cpu[0].configure(text=f"{cpu:.0f}%")
            self._s_cpu[1].configure(progress_color=cc); self._s_cpu[1].set(cpu/100)
            self._s_disk[0].configure(text=f"{f_gb:.0f} GB free"); self._s_disk[1].set(disk.used/disk.total)
            self._clock_lbl.configure(text=clk)
            self._dash_graphs["CPU %"].push(cpu)
            self._dash_graphs["RAM %"].push(vm.percent)
        self.after(0,apply)

    def _refresh_procs(self):
        rows=[]
        for p in psutil.process_iter(["pid","name","memory_info","cpu_percent"]):
            try:
                mi=p.info["memory_info"]
                if mi and mi.rss>4*1024*1024:
                    rows.append({"pid":p.info["pid"],"name":p.info["name"] or "?",
                                 "ram":mi.rss/1048576,"cpu":p.info["cpu_percent"] or 0})
            except Exception: pass
        srt=self._sort_var.get()
        if srt=="RAM": rows.sort(key=lambda x:x["ram"],reverse=True)
        elif srt=="CPU": rows.sort(key=lambda x:x["cpu"],reverse=True)
        else: rows.sort(key=lambda x:x["name"].lower())
        flt=self._flt_var.get().lower()
        if flt: rows=[r for r in rows if flt in r["name"].lower()]
        self.after(0,lambda: self._render_procs(rows[:MAX_ROWS]))

    def _refresh_network(self):
        cnts=psutil.net_io_counters(); now=time.time()
        dl=ul=0.0
        if self._net_prev:
            dt=max(now-self._net_time,0.001)
            dl=(cnts.bytes_recv-self._net_prev.bytes_recv)/dt
            ul=(cnts.bytes_sent-self._net_prev.bytes_sent)/dt
        self._net_prev=cnts; self._net_time=now
        dl_kb=dl/1024; ul_kb=ul/1024
        self._h_netd.append(dl_kb)
        self._live_stats["net"]=self._fmt_spd(dl)
        conns=[]
        pnames={p.pid:p.name() for p in psutil.process_iter(["pid","name"])}
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.status=="ESTABLISHED" and c.raddr:
                    conns.append({"proc":pnames.get(c.pid,f"PID {c.pid}"),
                                  "local":f"{c.laddr.ip}:{c.laddr.port}",
                                  "remote":f"{c.raddr.ip}:{c.raddr.port}",
                                  "status":c.status})
        except Exception: pass
        def apply():
            self._net_down.configure(text=self._fmt_spd(dl))
            self._net_up.configure(text=self._fmt_spd(ul))
            self._net_total.configure(text=self._fmt_bytes(cnts.bytes_recv))
            self._net_sent.configure(text=self._fmt_bytes(cnts.bytes_sent))
            self._s_net[0].configure(text=self._fmt_spd(dl)); self._s_net[1].set(min(dl/1e7,1))
            self._net_gd.push(dl_kb); self._net_gu.push(ul_kb)
            for w in self._conn_frame.winfo_children(): w.destroy()
            for i,c in enumerate(conns[:25]):
                bg=ROW1 if i%2==0 else ROW2
                row=ctk.CTkFrame(self._conn_frame,fg_color=bg,corner_radius=6,height=28)
                row.pack(fill="x",pady=1); row.pack_propagate(False)
                ctk.CTkLabel(row,text=c["proc"][:22],width=150,anchor="w",
                             font=ctk.CTkFont(size=11),text_color=TEXT).pack(side="left",padx=10,pady=2)
                ctk.CTkLabel(row,text=c["local"],width=170,anchor="w",
                             font=ctk.CTkFont(size=11),text_color=MUTED).pack(side="left",padx=4)
                ctk.CTkLabel(row,text=c["remote"],width=190,anchor="w",
                             font=ctk.CTkFont(size=11),text_color=TEAL).pack(side="left",padx=4)
        self.after(0,apply)

    def _refresh_diskio(self):
        counters=psutil.disk_io_counters(); now=time.time()
        read_spd=write_spd=0.0
        if self._disk_prev and "all" in self._disk_prev:
            dt=max(now-self._disk_time,0.001)
            prev=self._disk_prev["all"]
            read_spd =(counters.read_bytes -prev.read_bytes) /dt
            write_spd=(counters.write_bytes-prev.write_bytes)/dt
        self._disk_prev={"all":counters}; self._disk_time=now
        rk=read_spd/1024; wk=write_spd/1024
        self._h_disk.append(rk+wk)

        drives=[]
        for part in psutil.disk_partitions():
            try:
                u=psutil.disk_usage(part.mountpoint)
                drives.append({"mp":part.mountpoint,"total":u.total/1e9,
                               "used":u.used/1e9,"pct":u.percent})
            except Exception: pass

        proc_io=[]
        for p in psutil.process_iter(["pid","name"]):
            try:
                io=p.io_counters()
                if io.read_bytes+io.write_bytes > 1024*1024:
                    proc_io.append({"name":p.info["name"] or "?","pid":p.info["pid"],
                                    "rb":io.read_bytes,"wb":io.write_bytes})
            except Exception: pass
        proc_io.sort(key=lambda x:x["rb"]+x["wb"],reverse=True)

        def apply():
            self._dk_read.configure(text=self._fmt_spd(read_spd))
            self._dk_write.configure(text=self._fmt_spd(write_spd))
            self._dk_reads.configure(text=self._fmt_bytes(counters.read_bytes))
            self._dk_writes.configure(text=self._fmt_bytes(counters.write_bytes))
            self._s_iops[0].configure(text=self._fmt_spd(read_spd+write_spd))
            self._s_iops[1].set(min((read_spd+write_spd)/1e8,1))
            self._dk_gr.push(rk); self._dk_gw.push(wk)
            self._dash_graphs["Disk I/O KB/s"].push(rk+wk)

            for w in self._drive_frame.winfo_children(): w.destroy()
            for i,d in enumerate(drives):
                bg=ROW1 if i%2==0 else ROW2
                row=ctk.CTkFrame(self._drive_frame,fg_color=bg,corner_radius=7,height=32)
                row.pack(fill="x",pady=1); row.pack_propagate(False)
                pct_col=RED if d["pct"]>90 else ORANGE if d["pct"]>75 else GREEN
                ctk.CTkLabel(row,text=d["mp"],width=70,anchor="w",
                             font=ctk.CTkFont(size=12, weight="bold"),text_color=TEXT).pack(side="left",padx=12,pady=4)
                ctk.CTkLabel(row,text=f"{d['used']:.0f} / {d['total']:.0f} GB",width=150,
                             font=ctk.CTkFont(size=11),text_color=MUTED).pack(side="left",padx=4)
                ctk.CTkLabel(row,text=f"{d['pct']:.0f}% used",width=90,
                             font=ctk.CTkFont(size=11, weight="bold"),text_color=pct_col).pack(side="left",padx=4)
                bar=ctk.CTkProgressBar(row,height=6,width=200,corner_radius=3,
                                        fg_color="#1e1e3a",progress_color=pct_col)
                bar.set(d["pct"]/100); bar.pack(side="left",padx=8)

            for w in self._diskio_frame.winfo_children(): w.destroy()
            for i,p in enumerate(proc_io[:20]):
                bg=ROW1 if i%2==0 else ROW2
                row=ctk.CTkFrame(self._diskio_frame,fg_color=bg,corner_radius=6,height=30)
                row.pack(fill="x",pady=1); row.pack_propagate(False)
                ctk.CTkLabel(row,text=p["name"][:26],width=200,anchor="w",
                             font=ctk.CTkFont(size=11),text_color=TEXT).pack(side="left",padx=12,pady=3)
                ctk.CTkLabel(row,text=self._fmt_bytes(p["rb"]),width=100,
                             font=ctk.CTkFont(size=11),text_color=GREEN).pack(side="left",padx=4)
                ctk.CTkLabel(row,text=self._fmt_bytes(p["wb"]),width=100,
                             font=ctk.CTkFont(size=11),text_color=ORANGE).pack(side="left",padx=4)
        self.after(0,apply)

    def _refresh_gpu(self):
        try:
            h=pynvml.nvmlDeviceGetHandleByIndex(0)
            util=pynvml.nvmlDeviceGetUtilizationRates(h)
            mem=pynvml.nvmlDeviceGetMemoryInfo(h)
            temp=pynvml.nvmlDeviceGetTemperature(h,pynvml.NVML_TEMPERATURE_GPU)
            try: pwr=pynvml.nvmlDeviceGetPowerUsage(h)/1000; pwrlim=pynvml.nvmlDeviceGetPowerManagementLimit(h)/1000
            except Exception: pwr,pwrlim=0,115
            vu=mem.used/1e9; vt=mem.total/1e9; vp=mem.used/mem.total
            self._h_gpu.append(util.gpu)
            self._live_stats["gpu"]=f"{temp}C"
            self._live_stats["vram"]=f"{vu:.1f}/{vt:.0f}G"
            self._alerts.check("gpu_temp",temp,self._thr["gpu_temp"],"SysCtl - GPU",f"GPU is {temp}C")
            self._alerts.check("vram",vp*100,self._thr["vram"],"SysCtl - VRAM",f"VRAM {vp*100:.0f}%")
            data={"GPU Load":(f"{util.gpu}%",util.gpu/100),
                  "VRAM":(f"{vu:.1f}/{vt:.0f}G",vp),
                  "Temp":(f"{temp}C",min(temp/100,1)),
                  "Power":(f"{pwr:.0f}W",min(pwr/max(pwrlim,1),1))}
            def apply():
                self._s_gpu[0].configure(text=f"{vu:.1f}/{vt:.0f}GB"); self._s_gpu[1].set(vp)
                for nm,(lt,pct) in data.items():
                    if nm in self._gpu_w: self._gpu_w[nm][0].configure(text=lt); self._gpu_w[nm][1].set(min(pct,1))
                self._dash_graphs["GPU Load %"].push(util.gpu); self._gpu_graph.push(util.gpu)
            self.after(0,apply)
        except Exception: pass

    def _refresh_docker(self):
        try:
            r=subprocess.run(["docker","ps","--format",
                "{{.Names}}|{{.Image}}|{{.Status}}"],
                capture_output=True,text=True,timeout=3)
            if r.returncode!=0:
                self.after(0,lambda: self._docker_status.configure(
                    text="Docker not running or not installed",text_color=RED)); return
            lines=[l for l in r.stdout.strip().splitlines() if l]

            stats_r=subprocess.run(["docker","stats","--no-stream","--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"],
                capture_output=True,text=True,timeout=5)
            stats={}
            for l in stats_r.stdout.strip().splitlines():
                parts=l.split("|")
                if len(parts)==3: stats[parts[0]]={"cpu":parts[1],"mem":parts[2]}

            containers=[]
            for line in lines:
                parts=line.split("|")
                if len(parts)>=3:
                    nm=parts[0]; s=stats.get(nm,{})
                    containers.append({"name":nm,"image":parts[1],
                                       "status":parts[2],"cpu":s.get("cpu","--"),
                                       "mem":s.get("mem","--")})

            def apply():
                self._docker_status.configure(
                    text=f"{len(containers)} container(s) running",text_color=GREEN)
                for w in self._docker_frame.winfo_children(): w.destroy()
                if not containers:
                    ctk.CTkLabel(self._docker_frame,
                                 text="No running containers. Start one with: docker run ...",
                                 text_color=MUTED).pack(pady=20); return
                for i,c in enumerate(containers):
                    bg=ROW1 if i%2==0 else ROW2
                    row=ctk.CTkFrame(self._docker_frame,fg_color=bg,corner_radius=7)
                    row.pack(fill="x",pady=2)
                    sc=GREEN if "Up" in c["status"] else RED
                    ctk.CTkLabel(row,text=c["name"][:22],width=175,anchor="w",
                                 font=ctk.CTkFont(size=12, weight="bold"),text_color=TEXT).pack(side="left",padx=(14,4),pady=10)
                    ctk.CTkLabel(row,text=c["image"][:28],width=190,anchor="w",
                                 font=ctk.CTkFont(size=11),text_color=MUTED).pack(side="left",padx=4)
                    ctk.CTkLabel(row,text=c["cpu"],width=70,
                                 font=ctk.CTkFont(size=11),text_color=ORANGE).pack(side="left",padx=4)
                    ctk.CTkLabel(row,text=c["mem"][:20],width=160,
                                 font=ctk.CTkFont(size=11),text_color=BLUE).pack(side="left",padx=4)
                    ctk.CTkLabel(row,text=c["status"][:16],width=130,
                                 font=ctk.CTkFont(size=11),text_color=sc).pack(side="left",padx=4)
                    nm=c["name"]
                    ctk.CTkButton(row,text="Stop",width=60,height=26,
                                  fg_color=RED,hover_color="#c03030",font=ctk.CTkFont(size=11),
                                  command=lambda n=nm: self._docker_stop(n)).pack(side="right",padx=4,pady=8)
                    ctk.CTkButton(row,text="Restart",width=70,height=26,
                                  fg_color=ORANGE,hover_color="#c08020",font=ctk.CTkFont(size=11),
                                  command=lambda n=nm: self._docker_restart(n)).pack(side="right",padx=4)
                    ctk.CTkButton(row,text="Logs",width=60,height=26,
                                  fg_color=TEAL,hover_color="#1aaa99",font=ctk.CTkFont(size=11),
                                  command=lambda n=nm: self._docker_logs(n)).pack(side="right",padx=4)
            self.after(0,apply)
        except FileNotFoundError:
            self.after(0,lambda: self._docker_status.configure(
                text="Docker CLI not found - install Docker Desktop",text_color=RED))
        except Exception as e:
            self.after(0,lambda: self._docker_status.configure(text=f"Error: {e}",text_color=RED))

    def _docker_stop(self,name):
        threading.Thread(target=lambda: subprocess.run(["docker","stop",name],capture_output=True),
                         daemon=True).start()
        self._status(f"Stopping container: {name}")

    def _docker_restart(self,name):
        threading.Thread(target=lambda: subprocess.run(["docker","restart",name],capture_output=True),
                         daemon=True).start()
        self._status(f"Restarting container: {name}")

    def _docker_logs(self,name):
        def show():
            r=subprocess.run(["docker","logs","--tail","50",name],
                              capture_output=True,text=True)
            def render():
                dlg=ctk.CTkToplevel(self)
                dlg.title(f"Logs: {name}"); dlg.geometry("800x500")
                dlg.configure(fg_color=PANEL)
                txt=ctk.CTkTextbox(dlg,fg_color=BG,font=ctk.CTkFont("Courier New",11),
                                    text_color=GREEN)
                txt.pack(fill="both",expand=True,padx=10,pady=10)
                txt.insert("end",r.stdout or r.stderr or "(no logs)")
                txt.configure(state="disabled")
            self.after(0,render)
        threading.Thread(target=show,daemon=True).start()

    # ── PROFILES ───────────────────────────────
    def _ps(self,cmd):
        subprocess.run(["powershell","-WindowStyle","Hidden","-Command",cmd],capture_output=True)

    def _set_power(self,plan):
        out=subprocess.run(["powercfg","/list"],capture_output=True,text=True).stdout
        for line in out.splitlines():
            if plan.lower() in line.lower():
                guid=line.strip().split()[3]
                self._ps(f"powercfg /setactive {guid}"); return
    def _kill_by_name(self,*names):
        for p in psutil.process_iter(["name"]):
            try:
                if any(n.lower() in p.info["name"].lower() for n in names): p.kill()
            except Exception: pass

    def _profile_gaming(self):
        self._prof_status.configure(text="Gaming Mode pending confirmation...", text_color=ORANGE)
        def confirmed():
            def run():
                self._set_power("High performance")
                self._ps("Set-ItemProperty 'HKCU:\\System\\GameConfigStore' -Name GameDVR_Enabled -Value 0")
                self._ps("Set-ItemProperty 'HKCU:\\Software\\Microsoft\\GameBar' -Name AllowAutoGameMode -Value 1")
                self._ps("Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games' -Name 'GPU Priority' -Value 8")
                self._kill_by_name("OneDrive","Discord","Spotify"); gc.collect()
                self.after(0,lambda:(self._prof_lbl.configure(text="Mode: Gaming",text_color=ORANGE),
                                     self._prof_status.configure(text="Gaming Mode active",text_color=ORANGE)))
            threading.Thread(target=run, daemon=True).start()
        self._show_explain_dialog(
            "Gaming Mode",
            "Switch to high performance tuning and close selected background apps.",
            "Higher FPS and lower game interruptions.",
            "Advanced",
            confirmed,
            needs_admin=True,
        )

    def _profile_dev(self):
        self._prof_status.configure(text="Dev Mode pending confirmation...", text_color=BLUE)
        def confirmed():
            def run():
                self._set_power("Balanced")
                subprocess.run(["npm","cache","clean","--force"],capture_output=True)
                subprocess.run(["pip","cache","purge"],capture_output=True)
                gc.collect()
                self.after(0,lambda:(self._prof_lbl.configure(text="Mode: Dev",text_color=BLUE),
                                     self._prof_status.configure(text="Dev Mode active - caches cleaned",text_color=BLUE)))
            threading.Thread(target=run, daemon=True).start()
        self._show_explain_dialog(
            "Dev Mode",
            "Clean dev caches and tune for balanced multitasking.",
            "More predictable development performance.",
            "Needs Admin",
            confirmed,
            needs_admin=True,
        )

    def _profile_battery(self):
        self._prof_status.configure(text="Battery Mode pending confirmation...", text_color=GREEN)
        def confirmed():
            def run():
                self._set_power("Power saver")
                self._ps("Stop-Service DiagTrack -Force -ErrorAction SilentlyContinue")
                self._kill_by_name("Steam","EpicGames","OneDrive")
                self.after(0,lambda:(self._prof_lbl.configure(text="Mode: Battery",text_color=GREEN),
                                     self._prof_status.configure(text="Battery Mode active",text_color=GREEN)))
            threading.Thread(target=run, daemon=True).start()
        self._show_explain_dialog(
            "Battery Saver Mode",
            "Apply battery profile and close selected heavy background apps.",
            "Longer battery runtime.",
            "Needs Admin",
            confirmed,
            needs_admin=True,
        )

    def _profile_normal(self):
        self._prof_status.configure(text="Normal Mode pending confirmation...", text_color=PURPLE)
        def confirmed():
            def run():
                self._set_power("Balanced")
                self._ps("Set-ItemProperty 'HKCU:\\System\\GameConfigStore' -Name GameDVR_Enabled -Value 1")
                self.after(0,lambda:(self._prof_lbl.configure(text="Mode: Normal",text_color=GREEN),
                                     self._prof_status.configure(text="Normal Mode restored",text_color=PURPLE)))
            threading.Thread(target=run, daemon=True).start()
        self._show_explain_dialog(
            "Normal Mode",
            "Restore balanced defaults and standard settings.",
            "Return to everyday stable behavior.",
            "Safe",
            confirmed,
            needs_admin=False,
        )

    # ── ACTIONS ────────────────────────────────
    def _fmt_spd(self,bps):
        if bps>=1e6: return f"{bps/1e6:.1f} MB/s"
        if bps>=1e3: return f"{bps/1e3:.0f} KB/s"
        return f"{bps:.0f} B/s"

    def _fmt_bytes(self,b):
        if b>=1e9: return f"{b/1e9:.2f} GB"
        if b>=1e6: return f"{b/1e6:.1f} MB"
        return f"{b/1e3:.0f} KB"

    def _free_ram(self):
        self._status("Freeing RAM...")
        def run():
            gc.collect()
            freed=0
            try:
                import ctypes as _ct
                for proc in psutil.process_iter(["pid"]):
                    try:
                        h=_ct.windll.kernel32.OpenProcess(0x1F0FFF,False,proc.info["pid"])
                        if h: _ct.windll.psapi.EmptyWorkingSet(h); _ct.windll.kernel32.CloseHandle(h); freed+=1
                    except Exception: pass
            except Exception: pass
            self.after(0,lambda: self._status(f"RAM freed - trimmed {freed} processes"))
        threading.Thread(target=run,daemon=True).start()

    def _clean_temp(self):
        self._status("Cleaning...")
        def run():
            count=0
            for folder in [tempfile.gettempdir(),"C:\\Windows\\Temp"]:
                try:
                    for item in Path(folder).iterdir():
                        try:
                            if item.is_file(): item.unlink(); count+=1
                            elif item.is_dir(): shutil.rmtree(str(item),ignore_errors=True); count+=1
                        except Exception: pass
                except Exception: pass
            self.after(0,lambda: self._status(f"Cleaned {count} temp items"))
        threading.Thread(target=run,daemon=True).start()

    def _flush_dns(self):
        try:
            subprocess.run(["ipconfig","/flushdns"],capture_output=True,timeout=10)
            self._status("DNS cache flushed")
        except Exception as e: self._status(f"Error: {e}")

    def _boost_perf(self):
        def run():
            self._set_power("High performance")
            self._status("High Performance plan activated")
        self._show_explain_dialog(
            "Boost Power Plan",
            "Switch active Windows power plan to High Performance.",
            "Higher performance, potentially higher power draw.",
            "Needs Admin",
            run,
            needs_admin=True,
        )

    def _kill_hogs(self):
        hogs=[]
        for p in psutil.process_iter(["pid","name","memory_info"]):
            try:
                if p.info["memory_info"].rss>500*1048576:
                    hogs.append({"pid":p.info["pid"],"name":p.info["name"],"ram":p.info["memory_info"].rss/1048576})
            except Exception: pass
        if not hogs: self._status("No processes over 500 MB"); return
        dlg=ctk.CTkToplevel(self); dlg.title("Kill RAM Hogs"); dlg.geometry("480x360")
        dlg.configure(fg_color=PANEL); dlg.grab_set()
        ctk.CTkLabel(dlg,text="Select processes to kill",
                     font=ctk.CTkFont("Segoe UI",14,"bold"),text_color=RED).pack(pady=(18,8))
        sf=ctk.CTkScrollableFrame(dlg,height=200,fg_color=BG); sf.pack(fill="x",padx=20)
        checks={}
        for h in sorted(hogs,key=lambda x:x["ram"],reverse=True):
            v=ctk.BooleanVar(value=False); checks[h["pid"]]=v
            r=ctk.CTkFrame(sf,fg_color=CARD,corner_radius=6); r.pack(fill="x",pady=2)
            ctk.CTkCheckBox(r,variable=v,
                            text=f"{h['name'][:34]}  {h['ram']:.0f} MB  (PID {h['pid']})",
                            text_color=TEXT).pack(padx=12,pady=8)
        def confirm():
            killed=0
            for pid,var in checks.items():
                if var.get():
                    try: psutil.Process(pid).kill(); killed+=1
                    except Exception: pass
            dlg.destroy(); self._status(f"Killed {killed} processes")
        br=ctk.CTkFrame(dlg,fg_color="transparent"); br.pack(pady=12)
        ctk.CTkButton(br,text="Kill Selected",fg_color=RED,command=confirm).pack(side="left",padx=10)
        ctk.CTkButton(br,text="Cancel",command=dlg.destroy).pack(side="left",padx=10)

    def _open_tm(self):
        subprocess.Popen(["taskmgr.exe"]); self._status("Task Manager opened")

    def _kill(self,pid):
        try:
            p=psutil.Process(pid); nm=p.name(); p.kill(); self._status(f"Killed {nm} (PID {pid})")
        except psutil.AccessDenied: self._status("Access denied - run as Administrator")
        except psutil.NoSuchProcess: self._status("Process already gone")
        except Exception as e: self._status(f"Error: {e}")

    def _status(self,msg):
        try: self.after(0,lambda: self._status_lbl.configure(text=msg))
        except Exception: pass

    def on_close(self):
        self._alive=False
        self._sync_ui_settings()
        self._save_state()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
