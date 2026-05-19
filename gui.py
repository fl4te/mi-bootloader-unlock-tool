#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import subprocess
import sys
import os
import time
import json
import hashlib
import random
import signal
import ctypes
from datetime import datetime, timezone, timedelta
from pathlib import Path

def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for _p in ("ntplib", "pytz", "urllib3", "colorama"):
    try:
        __import__(_p)
    except ImportError:
        _install(_p)

import ntplib
import pytz
import urllib3

if os.name == "nt":
    ctypes.windll.winmm.timeBeginPeriod(1)

TZ_BEIJING  = pytz.timezone("Asia/Shanghai")
URL_STATUS  = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
URL_APPLY   = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"
UA          = "okhttp/4.12.0"
NTP_SERVERS = ["ntp0.ntp-servers.net", "ntp1.ntp-servers.net", "ntp2.ntp-servers.net"]

COLORS = {
    "bg":           "#0b0d13",
    "panel":        "#12151f",
    "panel2":       "#181c28",
    "border":       "#252a3a",
    "border_light": "#2e3448",
    "accent":       "#f97316",
    "accent_dim":   "#7c3a10",
    "accent2":      "#6366f1",
    "accent2_dim":  "#312e81",
    "success":      "#22c55e",
    "success_dim":  "#14532d",
    "warn":         "#f59e0b",
    "warn_dim":     "#78350f",
    "error":        "#f43f5e",
    "error_dim":    "#881337",
    "text":         "#e2e8f0",
    "text_dim":     "#94a3b8",
    "muted":        "#4b5675",
    "input_bg":     "#0f1119",
    "header_bg":    "#0e1018",
}

FONT_MONO  = "Courier New"
FONT_UI    = "Segoe UI" if os.name == "nt" else "SF Pro Display"

SLOT_TOKEN_MAP = {1: 1, 2: 2, 3: 1, 4: 2}

BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def now_beijing():
    return datetime.now(timezone.utc).astimezone(TZ_BEIJING)

def gen_device_id():
    return hashlib.sha1(f"{random.random()}-{time.time()}".encode()).hexdigest().upper()

def synced_time(start_bt, start_perf):
    return start_bt + timedelta(seconds=time.perf_counter() - start_perf)

def format_remaining(seconds):
    seconds = max(0, seconds)
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    ms     = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"

def get_ntp_beijing(log_cb):
    client = ntplib.NTPClient()
    for srv in NTP_SERVERS:
        try:
            t0 = time.perf_counter()
            r  = client.request(srv, version=3, timeout=3)
            lat = (time.perf_counter() - t0) * 1000
            bt  = datetime.fromtimestamp(r.tx_time, timezone.utc).astimezone(TZ_BEIJING)
            log_cb("ok",    f"NTP sync OK  ← {srv}  ({lat:.1f} ms)")
            log_cb("debug", f"offset={r.offset*1000:.2f} ms | delay={r.delay*1000:.2f} ms")
            return bt
        except Exception as e:
            log_cb("warn", f"NTP failed: {srv} ({e})")
    bt = now_beijing()
    log_cb("warn", "Falling back to local system clock")
    return bt

def build_headers(token, device_id):
    return {"Cookie": (
        f"new_bbs_serviceToken={token}; "
        f"versionCode=500411; versionName=5.4.11; deviceId={device_id};"
    )}

def make_session():
    return urllib3.PoolManager(
        maxsize=10,
        retries=urllib3.Retry(total=1, backoff_factor=0),
        timeout=urllib3.Timeout(connect=2.0, read=5.0),
    )

def check_status(session, token, device_id, log_cb):
    try:
        r   = session.request("GET", URL_STATUS, headers=build_headers(token, device_id))
        raw = r.data.decode("utf-8")
        try: r.close()
        except: r.release_conn()
        data     = json.loads(raw)
        code     = data.get("code")
        if code == 100004:
            log_cb("error", "Token expired or invalid — please refresh it.")
            return False
        info     = data.get("data", {})
        is_pass  = info.get("is_pass")
        btn      = info.get("button_state")
        log_cb("debug", f"Status → is_pass={is_pass} button={btn}")
        if is_pass == 4 and btn == 1:
            log_cb("ok",   "Account READY — burst window available ✓")
            return True
        elif is_pass == 1:
            log_cb("ok",   "Account already approved! Nothing to do.")
            return False
        else:
            log_cb("error", f"Criteria not met (is_pass={is_pass}, btn={btn})")
            return False
    except Exception as e:
        log_cb("error", f"Status check exception: {e}")
        return False

def fire(session, token, device_id, log_cb):
    try:
        t0  = time.perf_counter()
        r   = session.request("POST", URL_APPLY,
                              headers=build_headers(token, device_id),
                              body=b'{"is_retry":true}')
        lat = (time.perf_counter() - t0) * 1000
        raw = r.data.decode("utf-8")
        try: r.close()
        except: r.release_conn()
        log_cb("debug", f"POST {lat:.1f} ms  →  {raw[:120]}")
        return json.loads(raw)
    except Exception as e:
        log_cb("error", f"Fire exception: {e}")
        return None

def handle_resp(resp, log_cb):
    code = resp.get("code")
    if code != 0:
        log_cb("error", f"API rejected (code={code})")
        return False
    data     = resp.get("data", {})
    result   = data.get("apply_result")
    deadline = data.get("deadline_format", "")
    if result == 1:
        log_cb("ok",   "APPROVAL GRANTED SUCCESSFULLY")
        return True
    elif result == 3:
        log_cb("warn", f"Quota full — resets at: {deadline}")
    elif result == 4:
        log_cb("error", f"Rate-limited — blocked until: {deadline}")
    else:
        log_cb("warn", f"Unknown result state: {resp}")
    return False


class SlotWorker:
    def __init__(self, slot_num: int, token: str, cfg: dict, log_cb, status_cb, stop_event):
        self.slot       = slot_num
        self.token      = token
        self.cfg        = cfg
        self.log        = log_cb
        self.set_status = status_cb
        self.stop       = stop_event
        self.thread     = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        cfg        = self.cfg
        device_id  = gen_device_id()
        session    = make_session()
        slot       = self.slot

        self.log("info", f"[Slot {slot}] Starting — token #{SLOT_TOKEN_MAP[slot]}")
        self.set_status("checking")

        if not check_status(session, self.token, device_id, self.log):
            self.set_status("stopped")
            return

        start_bt   = get_ntp_beijing(self.log)
        start_perf = time.perf_counter()

        if cfg["skip_timing"]:
            target = start_bt.replace(
                hour=cfg["fire_hour"], minute=cfg["fire_min"],
                second=cfg["fire_sec"], microsecond=0)
            self.log("warn", f"[Slot {slot}] Manual target: {target.strftime('%H:%M:%S Beijing')}")
        else:
            target = (start_bt + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            self.log("warn", f"[Slot {slot}] Auto target: {target.strftime('%Y-%m-%d %H:%M:%S Beijing')}")

        fire_start = target - timedelta(milliseconds=cfg["offset_ms"])

        self.set_status("waiting")
        self.log("info", f"[Slot {slot}] Waiting for fire window…")

        while not self.stop.is_set():
            now  = synced_time(start_bt, start_perf)
            diff = (fire_start - now).total_seconds()
            self.set_status(f"T-{format_remaining(diff)}")
            if diff <= 0:
                break
            if diff > 1:       time.sleep(0.25)
            elif diff > 0.1:   time.sleep(0.01)
            elif diff > 0.01:  time.sleep(0.001)
            else:              time.sleep(0.0001)

        if self.stop.is_set():
            self.set_status("stopped")
            return

        self.set_status("FIRING")
        self.log("ok",  f"[Slot {slot}] Burst engine engaged!")
        success = False

        for i in range(cfg["burst_count"]):
            if self.stop.is_set():
                break
            shot_target = target + timedelta(milliseconds=i * cfg["burst_interval_ms"])
            while not self.stop.is_set():
                diff = (shot_target - synced_time(start_bt, start_perf)).total_seconds()
                if diff <= 0:
                    break
                time.sleep(max(diff * 0.7, 0.0001))

            actual      = synced_time(start_bt, start_perf)
            timing_err  = (actual - shot_target).total_seconds() * 1000
            self.log("info",
                f"[Slot {slot}] Shot {i+1:02}/{cfg['burst_count']:02}  "
                f"target={shot_target.strftime('%H:%M:%S.%f')[:-3]}  "
                f"actual={actual.strftime('%H:%M:%S.%f')[:-3]}  "
                f"err={timing_err:+.2f}ms")

            resp = fire(session, self.token, device_id, self.log)
            if resp and handle_resp(resp, self.log):
                success = True
                self.log("ok", f"[Slot {slot}] Resolved on shot #{i+1}")
                break

        if success:
            self.set_status("APPROVED")
        else:
            self.set_status("Exhausted")
            self.log("warn", f"[Slot {slot}] Burst complete — no approval. Retry tomorrow 00:00 Beijing.")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MI Bootloader Unlock Tool")
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)
        self.minsize(960, 660)

        self._stop_event = threading.Event()
        self._workers    = []

        self._build_ui()
        self._load_files()
        self._tick_clock()
        
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)


    def _load_files(self):
        tf = BASE_DIR / "token.txt"
        if tf.exists():
            lines = tf.read_text().splitlines()
            if len(lines) >= 1: self._token1_var.set(lines[0].strip())
            if len(lines) >= 2: self._token2_var.set(lines[1].strip())

        tsf = BASE_DIR / "timeshift.txt"
        if tsf.exists():
            self._log("info", f"timeshift.txt found at {tsf} (not used by GUI directly)")

    def _save_tokens(self):
        tf = BASE_DIR / "token.txt"
        tf.write_text(f"{self._token1_var.get().strip()}\n{self._token2_var.get().strip()}\n")
        self._log("ok", "token.txt saved ✓")


    def _tick_clock(self):
        bt = now_beijing()
        self._clock_var.set(bt.strftime("%H:%M:%S") + "  Beijing")
        self.after(500, self._tick_clock)


    def _log(self, level: str, msg: str):
        tag_map = {
            "ok":    "ok",
            "info":  "info",
            "warn":  "warn",
            "error": "error",
            "debug": "debug",
        }
        ts  = now_beijing().strftime("%H:%M:%S.%f")[:-3]
        tag = tag_map.get(level, "info")
        prefix = {"ok":"OK  ", "info":"INFO", "warn":"WARN", "error":"ERR ",
                  "debug":"DBG "}.get(level, "    ")

        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{ts}]  {prefix}  {msg}\n", tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")


    def _make_status_cb(self, slot_idx: int):
        def _cb(status: str):
            self.after(0, lambda: self._slot_status[slot_idx].set(status))
        return _cb

    def _make_log_cb(self):
        def _cb(level, msg):
            self.after(0, lambda: self._log(level, msg))
        return _cb


    def _on_run(self):
        t1 = self._token1_var.get().strip()
        t2 = self._token2_var.get().strip()
        if not t1 or not t2:
            messagebox.showerror("Missing tokens",
                "Please fill in both Token 1 and Token 2 before running.")
            return

        self._stop_event.clear()
        self._workers.clear()
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal",
                                 bg=COLORS["error"], fg="white",
                                 activebackground="#be123c")

        tokens = {1: t1, 2: t2}
        cfg = {
            "skip_timing":       self._skip_timing_var.get(),
            "fire_hour":         self._fire_hour_var.get(),
            "fire_min":          self._fire_min_var.get(),
            "fire_sec":          self._fire_sec_var.get(),
            "offset_ms":         self._offset_ms_var.get(),
            "burst_interval_ms": self._burst_interval_var.get(),
            "burst_count":       self._burst_count_var.get(),
        }

        enabled_slots = [i+1 for i, v in enumerate(self._slot_enabled) if v.get()]
        if not enabled_slots:
            messagebox.showwarning("No slots", "Enable at least one slot.")
            self._run_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            return

        self._log("info", f"Starting slots: {enabled_slots}")

        for slot in enabled_slots:
            tok      = tokens[SLOT_TOKEN_MAP[slot]]
            log_cb   = self._make_log_cb()
            status_cb= self._make_status_cb(slot - 1)
            w = SlotWorker(slot, tok, cfg, log_cb, status_cb, self._stop_event)
            self._workers.append(w)
            w.start()

    def _on_stop(self):
        self._stop_event.set()
        self._log("warn", "Stop requested — workers will halt at next checkpoint.")
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled",
                                 bg=COLORS["border"], fg=COLORS["text_dim"],
                                 activebackground=COLORS["error"],
                                 activeforeground="white")

    def _on_window_close(self):
        self._on_stop()
        self.destroy()

    def _on_clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")


    def _build_ui(self):
        C = COLORS

        hdr = tk.Frame(self, bg=C["header_bg"], height=62)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        left_hdr = tk.Frame(hdr, bg=C["header_bg"])
        left_hdr.pack(side="left", padx=20, pady=0, fill="y")

        badge = tk.Label(left_hdr, text=" MI ", bg=C["accent"], fg="white",
                         font=(FONT_MONO, 11, "bold"), relief="flat", pady=2)
        badge.pack(side="left", padx=(0, 12), pady=16)

        title_frame = tk.Frame(left_hdr, bg=C["header_bg"])
        title_frame.pack(side="left", fill="y", pady=12)
        tk.Label(title_frame, text="Bootloader Unlock Tool",
                 bg=C["header_bg"], fg=C["text"],
                 font=(FONT_UI, 13, "bold")).pack(anchor="w")
        tk.Label(title_frame, text="Xiaomi Global · SGP API",
                 bg=C["header_bg"], fg=C["muted"],
                 font=(FONT_UI, 8)).pack(anchor="w")

        right_hdr = tk.Frame(hdr, bg=C["header_bg"])
        right_hdr.pack(side="right", padx=20, fill="y")
        self._clock_var = tk.StringVar(value="")
        tk.Label(right_hdr, text="LOCAL TIME IN",
                 bg=C["header_bg"], fg=C["muted"],
                 font=(FONT_UI, 7, "bold")).pack(anchor="e", pady=(14, 0))
        tk.Label(right_hdr, textvariable=self._clock_var,
                 bg=C["header_bg"], fg=C["accent2"],
                 font=(FONT_MONO, 13, "bold")).pack(anchor="e")

        tk.Frame(self, bg=C["accent"], height=2).pack(fill="x")

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True)

        paned = tk.PanedWindow(body, orient="horizontal",
                               bg=C["border"],
                               sashwidth=5,
                               sashrelief="flat",
                               opaqueresize=True,
                               handlesize=0)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg=C["bg"])
        right = tk.Frame(paned, bg=C["bg"])

        paned.add(left,  minsize=260, width=320, stretch="never")
        paned.add(right, minsize=400, stretch="always")

        self._build_config(left)
        self._build_slots_and_log(right)


    def _section(self, parent, title):
        outer = tk.Frame(parent, bg=COLORS["panel"],
                         highlightbackground=COLORS["border_light"],
                         highlightthickness=1)
        outer.pack(fill="x", padx=10, pady=(10, 0))
        accent_bar = tk.Frame(outer, bg=COLORS["accent"], width=3)
        accent_bar.pack(side="left", fill="y")
        content = tk.Frame(outer, bg=COLORS["panel"])
        content.pack(side="left", fill="both", expand=True)
        tk.Label(content, text=title, bg=COLORS["panel"], fg=COLORS["text_dim"],
                 font=(FONT_UI, 8, "bold")).pack(anchor="w", padx=10, pady=(7, 2))
        inner = tk.Frame(content, bg=COLORS["panel"])
        inner.pack(fill="x", padx=10, pady=(0, 10))
        return inner

    def _row(self, parent, label, widget_factory):
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=COLORS["panel"], fg=COLORS["text_dim"],
                 font=(FONT_UI, 8), width=20, anchor="w").pack(side="left")
        w = widget_factory(row)
        w.pack(side="left", fill="x", expand=True)
        return w

    def _entry(self, parent, textvariable, **kw):
        return tk.Entry(parent, textvariable=textvariable,
                        bg=COLORS["input_bg"], fg=COLORS["text"],
                        insertbackground=COLORS["accent"],
                        relief="flat", font=(FONT_MONO, 9),
                        highlightbackground=COLORS["border_light"],
                        highlightcolor=COLORS["accent2"],
                        highlightthickness=1, **kw)

    def _spinbox(self, parent, var, from_, to, width=7):
        return tk.Spinbox(parent, textvariable=var,
                          from_=from_, to=to, width=width,
                          bg=COLORS["input_bg"], fg=COLORS["text"],
                          buttonbackground=COLORS["border_light"],
                          relief="flat", font=(FONT_MONO, 9),
                          highlightbackground=COLORS["border_light"],
                          highlightthickness=1)

    def _build_config(self, parent):
        C = COLORS

        canvas = tk.Canvas(parent, bg=C["bg"], bd=0, highlightthickness=0)
        sb     = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=C["bg"])
        win   = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(e):
            canvas.itemconfig(win, width=e.width)

        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

        sec = self._section(inner, "TOKENS")
        self._token1_var = tk.StringVar()
        self._token2_var = tk.StringVar()
        
        self._token1_entry = self._row(sec, "Token 1", lambda p: self._entry(p, self._token1_var, show="*"))
        self._token2_entry = self._row(sec, "Token 2", lambda p: self._entry(p, self._token2_var, show="*"))

        btn_row = tk.Frame(sec, bg=C["panel"])
        btn_row.pack(fill="x", pady=(4, 0))
        tk.Button(btn_row, text="👁  Show/Hide",
                  bg=C["border_light"], fg=C["text_dim"],
                  activebackground=C["accent2_dim"],
                  activeforeground=C["text"],
                  relief="flat", font=(FONT_UI, 8),
                  cursor="hand2", padx=6, pady=3,
                  command=self._toggle_token_vis).pack(side="left", padx=(0, 6))
        tk.Button(btn_row, text="💾  Save",
                  bg=C["accent2_dim"], fg=C["text"],
                  activebackground=C["accent2"],
                  activeforeground="white",
                  relief="flat", font=(FONT_UI, 8, "bold"),
                  cursor="hand2", padx=6, pady=3,
                  command=self._save_tokens).pack(side="left")

        sec2 = self._section(inner, "ENABLED SLOTS")
        self._slot_enabled = [tk.BooleanVar(value=True) for _ in range(4)]
        sf = tk.Frame(sec2, bg=C["panel"])
        sf.pack(fill="x")
        sf.columnconfigure(0, weight=1)
        sf.columnconfigure(1, weight=1)
        for i in range(4):
            r, c = divmod(i, 2)
            tk.Checkbutton(sf, text=f"Slot {i+1}",
                           variable=self._slot_enabled[i],
                           bg=C["panel"], fg=C["text"],
                           selectcolor=C["accent_dim"],
                           activebackground=C["panel"],
                           activeforeground=C["accent"],
                           font=(FONT_UI, 9)).grid(row=r, column=c, sticky="w", padx=6, pady=2)

        sec3 = self._section(inner, "TIMING")
        self._skip_timing_var = tk.BooleanVar(value=False)
        tk.Checkbutton(sec3, text="Manual fire time (skip auto-midnight)",
                       variable=self._skip_timing_var,
                       bg=C["panel"], fg=C["text"],
                       selectcolor=C["accent_dim"],
                       activebackground=C["panel"],
                       activeforeground=C["accent"],
                       font=(FONT_UI, 9),
                       command=self._toggle_manual_time).pack(anchor="w")

        self._manual_frame = tk.Frame(sec3, bg=C["panel"])
        self._manual_frame.pack(fill="x")
        self._fire_hour_var = tk.IntVar(value=19)
        self._fire_min_var  = tk.IntVar(value=37)
        self._fire_sec_var  = tk.IntVar(value=0)
        hf = tk.Frame(self._manual_frame, bg=C["panel"])
        hf.pack(anchor="w")
        for label, var, hi in [("HH", self._fire_hour_var, 23),
                                ("MM", self._fire_min_var,  59),
                                ("SS", self._fire_sec_var,  59)]:
            tk.Label(hf, text=label, bg=C["panel"], fg=C["text_dim"],
                     font=(FONT_UI, 8, "bold")).pack(side="left", padx=(6,2))
            self._spinbox(hf, var, 0, hi, width=4).pack(side="left", padx=2)
        self._toggle_manual_time()

        sec4 = self._section(inner, "BURST CONFIG")
        self._offset_ms_var     = tk.IntVar(value=120)
        self._burst_interval_var= tk.IntVar(value=50)
        self._burst_count_var   = tk.IntVar(value=10)

        self._row(sec4, "Pre-fire offset ms",
                  lambda p: self._spinbox(p, self._offset_ms_var, 0, 5000))
        self._row(sec4, "Burst interval ms",
                  lambda p: self._spinbox(p, self._burst_interval_var, 1, 1000))
        self._row(sec4, "Burst count",
                  lambda p: self._spinbox(p, self._burst_count_var, 1, 50))

        btn_sec = tk.Frame(inner, bg=C["bg"])
        btn_sec.pack(fill="x", padx=10, pady=12)

        self._run_btn = tk.Button(btn_sec, text="▶  RUN",
                                  bg=C["accent"], fg="white",
                                  activebackground="#ea6810",
                                  font=(FONT_UI, 11, "bold"),
                                  relief="flat", cursor="hand2",
                                  pady=8,
                                  command=self._on_run)
        self._run_btn.pack(fill="x", pady=(0, 6))

        self._stop_btn = tk.Button(btn_sec, text="■  STOP",
                                   bg=C["border"], fg=C["text_dim"],
                                   activebackground=C["error"],
                                   activeforeground="white",
                                   font=(FONT_UI, 11, "bold"),
                                   relief="flat", cursor="hand2",
                                   pady=8,
                                   state="disabled",
                                   command=self._on_stop)
        self._stop_btn.pack(fill="x")

    def _toggle_token_vis(self):
        for entry_name in ("_token1_entry", "_token2_entry"):
            w = getattr(self, entry_name, None)
            if w:
                w.config(show="" if w.cget("show") == "*" else "*")

    def _toggle_manual_time(self):
        state = "normal" if self._skip_timing_var.get() else "disabled"
        for child in self._manual_frame.winfo_children():
            for subchild in child.winfo_children() if hasattr(child, "winfo_children") else []:
                try: subchild.configure(state=state)
                except: pass
            try: child.configure(state=state)
            except: pass


    def _build_slots_and_log(self, parent):
        C = COLORS

        slot_frame = tk.Frame(parent, bg=C["bg"])
        slot_frame.pack(fill="x", padx=10, pady=10)

        self._slot_status = [tk.StringVar(value="idle") for _ in range(4)]
        slot_frame.columnconfigure(0, weight=1)
        slot_frame.columnconfigure(1, weight=1)

        for i in range(4):
            r, c  = divmod(i, 2)
            pane  = tk.Frame(slot_frame, bg=C["panel"],
                             highlightbackground=C["border_light"],
                             highlightthickness=1)
            pane.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")

            hrow = tk.Frame(pane, bg=C["panel"])
            hrow.pack(fill="x", padx=8, pady=(8, 0))
            slot_badge = tk.Label(hrow, text=f"{i+1}",
                                  bg=C["accent"], fg="white",
                                  font=(FONT_MONO, 9, "bold"), width=2, pady=1)
            slot_badge.pack(side="left", padx=(0, 6))
            tk.Label(hrow, text=f"SLOT {i+1}",
                     bg=C["panel"], fg=C["text"],
                     font=(FONT_UI, 10, "bold")).pack(side="left", anchor="w")

            tk.Label(pane,
                     text=f"Token #{SLOT_TOKEN_MAP[i+1]}",
                     bg=C["panel"], fg=C["muted"],
                     font=(FONT_UI, 8)).pack(anchor="w", padx=8)

            status_lbl = tk.Label(pane, textvariable=self._slot_status[i],
                     bg=C["panel"], fg=C["accent2"],
                     font=(FONT_MONO, 9, "bold"))
            status_lbl.pack(anchor="w", padx=8, pady=(2, 8))

        log_header = tk.Frame(parent, bg=C["bg"])
        log_header.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(log_header, text="LIVE LOG",
                 bg=C["bg"], fg=C["text_dim"],
                 font=(FONT_UI, 9, "bold")).pack(side="left")
        tk.Button(log_header, text="✕ Clear",
                  bg=C["border"], fg=C["text_dim"],
                  activebackground=C["border_light"],
                  activeforeground=C["text"],
                  relief="flat", font=(FONT_UI, 8),
                  cursor="hand2", padx=6, pady=2,
                  command=self._on_clear_log).pack(side="right")

        self._log_box = scrolledtext.ScrolledText(
            parent, state="disabled", wrap="word",
            bg=C["input_bg"], fg=C["text"],
            font=(FONT_MONO, 8),
            relief="flat",
            insertbackground=C["accent"],
            selectbackground=C["accent2_dim"],
            selectforeground=C["text"],
            height=22,
            padx=8, pady=6,
        )
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for tag, color in [("ok",    C["success"]),
                           ("info",  C["text"]),
                           ("warn",  C["warn"]),
                           ("error", C["error"]),
                           ("debug", C["muted"])]:
            self._log_box.tag_configure(tag, foreground=color)
        self._log_box.tag_configure("ok",    font=(FONT_MONO, 8, "bold"))
        self._log_box.tag_configure("error", font=(FONT_MONO, 8, "bold"))

        self._log("info", "GUI loaded. Fill tokens, configure, then press RUN.")


def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
