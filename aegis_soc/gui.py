"""
AEGIS IDEA 3 — SOC GUI (หน้าจอควบคุมหลัก)
รวมฟีเจอร์: ARM/DISARM + ยืนยันคำสั่งซ้อน, ACK tracking, สถานะอุปกรณ์สด,
Log แบ่งระดับความรุนแรง + กรอง, Incident banner
"""
import csv
import ipaddress
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog

from . import comms, config, security
from . import database as db
from .mqtt_client import MQTTManager
from .theme import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_BLUE,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_DANGER_HL,
    COLOR_GOOD,
    COLOR_MUTED,
    COLOR_PANEL,
    COLOR_PANEL_ALT,
    COLOR_PURPLE,
    COLOR_SUCCESS,
    COLOR_SUCCESS_HL,
    COLOR_TEXT,
    COLOR_WARN,
    COLOR_WARN_HL,
    FONT_BTN,
    FONT_BTN_SM,
    FONT_HINT,
    FONT_MONO,
    FONT_SUB,
    FONT_TITLE,
    LEVEL_COLORS,
    Card,
    ScrollFrame,
    Section,
    make_hint,
)
from .wizard import IncidentRecoveryWizard

FILTER_ALL = "ทั้งหมด"
FILTER_WARN = "WARN ขึ้นไป"
FILTER_CRIT = "เฉพาะ CRITICAL"
_LEVEL_RANK = {"INFO": 0, "WARN": 1, "CRITICAL": 2}


class AegisAdminGUI:
    def __init__(self, root, mqtt_manager):
        self.root = root
        self.mqtt = mqtt_manager
        self.tg_pin_fails = 0          # จำนวนครั้งใส่ PIN ผิดทาง Telegram
        self.tg_locked_until = 0       # ล็อกจนถึงเวลาไหน (timestamp)

        # ---- operational state ----
        self.armed = True                 # ARMED = เฝ้าระวังปกติ, DISARMED = โหมดซ่อมบำรุง
        self.locked = False               # ล็อกเมื่อกรอก PIN ผิดหลายครั้ง
        self.pin_attempts = 0
        self.pending_cmd = None           # {'action','ts'} คำสั่งที่รอ ACK
        self.last_heartbeat_sent_ts = time.time()
        self.log_buffer = []              # (message, level) ทุกบรรทัด เพื่อกรองใหม่ได้

        self.root.title("AEGIS IDEA 3 — Cyber-Physical SOC Command Center")
        self.root.geometry("1120x780")
        self.root.minsize(1000, 680)
        self.root.config(bg=COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._start_background_heartbeat()
        self._tick_clock()
        self._tick_monitors()
        self._emit_startup_warnings()

    # =========================================================
    # UI BUILD
    # =========================================================
    def _build_ui(self):
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self._build_header()

        wrap = tk.Frame(self.root, bg=COLOR_BG, width=364)
        wrap.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=(0, 8))
        wrap.grid_propagate(False)
        scroll = ScrollFrame(wrap)
        scroll.pack(fill="both", expand=True)
        self._build_sidebar(scroll.inner)

        main = tk.Frame(self.root, bg=COLOR_BG)
        main.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 8))
        self._build_main_panel(main)
        self._build_footer()

    def _build_header(self):
        header = tk.Frame(self.root, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=16)

        left = tk.Frame(header, bg=COLOR_PANEL)
        left.pack(side="left", fill="y", padx=16, pady=12)
        tk.Label(left, text="🛡️  AEGIS IDEA 3", font=FONT_TITLE, fg=COLOR_ACCENT, bg=COLOR_PANEL).pack(anchor="w")
        tk.Label(left, text="Cyber-Physical Lockdown · Security Operations Center", font=FONT_SUB,
                 fg=COLOR_MUTED, bg=COLOR_PANEL).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=COLOR_PANEL)
        right.pack(side="right", fill="y", padx=16, pady=10)
        self.lbl_clock = tk.Label(right, text="--:--:--", font=("Segoe UI", 16, "bold"),
                                  fg=COLOR_TEXT, bg=COLOR_PANEL)
        self.lbl_clock.pack(anchor="e")
        badges = tk.Frame(right, bg=COLOR_PANEL)
        badges.pack(anchor="e", pady=(2, 0))
        self.lbl_conn = tk.Label(badges, text="🟡 broker…", font=("Segoe UI", 8, "bold"),
                                 fg=COLOR_WARN_HL, bg=COLOR_PANEL)
        self.lbl_conn.pack(side="left", padx=(0, 10))
        self.lbl_device = tk.Label(badges, text="⚪ ESP32: ยังไม่พบ", font=("Segoe UI", 8, "bold"),
                                   fg=COLOR_MUTED, bg=COLOR_PANEL)
        self.lbl_device.pack(side="left")

    def _build_sidebar(self, parent):
        # ---- System control: ARM / DISARM ----
        self.sys_section = Section(parent, "🎚️ โหมดระบบ (SYSTEM CONTROL)", accent=COLOR_SUCCESS)
        self.sys_section.pack(fill="x", pady=(0, 10))
        self.card_mode = Card(self.sys_section.body, accent=COLOR_SUCCESS)
        self.card_mode.pack(fill="x", pady=(0, 6))
        self.lbl_mode = tk.Label(self.card_mode.body, text="🟢 ARMED — เฝ้าระวัง", font=("Segoe UI", 13, "bold"),
                                 fg=COLOR_GOOD, bg=COLOR_PANEL)
        self.lbl_mode.pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(self.card_mode.body, text="ARMED = ระบบเฝ้าระวังและพร้อมตอบโต้เต็มรูปแบบ",
                 font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL, wraplength=290,
                 justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        self.btn_arm = tk.Button(self.sys_section.body, text="🔧  สลับเป็นโหมดซ่อมบำรุง (DISARM)", font=FONT_BTN_SM,
                                 fg="white", bg=COLOR_WARN, activebackground=COLOR_WARN_HL, bd=0,
                                 height=2, cursor="hand2", command=self.toggle_arm)
        self.btn_arm.pack(fill="x")
        make_hint(self.sys_section.body, "โหมดซ่อมบำรุงจะปิดปุ่มตัดเน็ตชั่วคราว (กันสั่งพลาดตอนแก้ระบบ) "
                                         "แต่ยังส่ง heartbeat อยู่ ESP32 จึงไม่ตัดเน็ตเอง").pack(anchor="w", pady=(4, 0))

        # ---- Live telemetry ----
        tel = Section(parent, "⚡ สถานะระบบสด (LIVE TELEMETRY)", accent=COLOR_ACCENT)
        tel.pack(fill="x", pady=(0, 10))
        self.card_uplink = Card(tel.body, accent=COLOR_ACCENT)
        self.card_uplink.pack(fill="x", pady=(0, 6))
        tk.Label(self.card_uplink.body, text="สถานะ UPLINK", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_uplink = tk.Label(self.card_uplink.body, text="🟢  NORMAL", font=("Segoe UI", 14, "bold"),
                                   fg=COLOR_ACCENT, bg=COLOR_PANEL)
        self.lbl_uplink.pack(anchor="w", padx=12, pady=(0, 8))

        row = tk.Frame(tel.body, bg=COLOR_PANEL)
        row.pack(fill="x")
        self.card_rssi = Card(row, accent=COLOR_GOOD)
        self.card_rssi.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(self.card_rssi.body, text="📶 RSSI", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_rssi = tk.Label(self.card_rssi.body, text="-- dBm", font=("Segoe UI", 12, "bold"),
                                 fg=COLOR_GOOD, bg=COLOR_PANEL)
        self.lbl_rssi.pack(anchor="w", padx=10, pady=(0, 8))
        self.card_heap = Card(row, accent=COLOR_PURPLE)
        self.card_heap.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(self.card_heap.body, text="💾 Free Heap", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_heap = tk.Label(self.card_heap.body, text="-- B", font=("Segoe UI", 12, "bold"),
                                 fg=COLOR_PURPLE, bg=COLOR_PANEL)
        self.lbl_heap.pack(anchor="w", padx=10, pady=(0, 8))

        self.card_deadman = Card(tel.body, accent=COLOR_GOOD)
        self.card_deadman.pack(fill="x", pady=(6, 0))
        tk.Label(self.card_deadman.body, text="🐕‍🦺 DEAD MAN'S SWITCH", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_deadman = tk.Label(self.card_deadman.body, text="60s", font=("Segoe UI", 20, "bold"),
                                    fg=COLOR_GOOD, bg=COLOR_PANEL)
        self.lbl_deadman.pack(anchor="w", padx=12)
        tk.Label(self.card_deadman.body, text="เวลาก่อน ESP32 ตัด uplink เอง ถ้าไม่ได้รับ heartbeat",
                 font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL, wraplength=290,
                 justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        # ---- Operational controls ----
        ctl = Section(parent, "🕹️ ควบคุมการทำงาน (ต้องใส่ PIN)", accent=COLOR_DANGER)
        ctl.pack(fill="x", pady=(0, 10))
        self.btn_cut = tk.Button(ctl.body, text="🛑  ตัดเน็ตฉุกเฉิน (CUT_UPLINK)", font=FONT_BTN, fg="white",
                                 bg=COLOR_DANGER, activebackground=COLOR_DANGER_HL, activeforeground="white",
                                 height=2, bd=0, cursor="hand2", command=self.on_cut_clicked)
        self.btn_cut.pack(fill="x")
        make_hint(ctl.body, "ต้องใส่ PIN + พิมพ์ CONFIRM ยืนยันซ้ำ "
                            "(จะถาม IP ผู้โจมตีเพื่อบล็อก UFW + แนบ Telegram)").pack(anchor="w", pady=(4, 8))
        self.btn_restore = tk.Button(ctl.body, text="✅  คืนค่าระบบปกติ (RESTORE_UPLINK)", font=FONT_BTN,
                                     fg="white", bg=COLOR_SUCCESS, activebackground=COLOR_SUCCESS_HL,
                                     activeforeground="white", height=2, bd=0, cursor="hand2",
                                     command=self.on_restore_clicked)
        self.btn_restore.pack(fill="x")
        make_hint(ctl.body, "สั่งต่อสาย Uplink กลับ หลังจัดการภัยเรียบร้อยแล้ว").pack(anchor="w", pady=(4, 0))

        # ---- Recovery ----
        rec = Section(parent, "🧯 กู้คืนหลังเหตุการณ์ (INCIDENT RECOVERY)", accent=COLOR_WARN)
        rec.pack(fill="x")
        self.btn_recovery = tk.Button(rec.body, text="🧯  เปิด Incident Recovery Wizard", font=FONT_BTN,
                                      fg="white", bg=COLOR_WARN, activebackground=COLOR_WARN_HL, bd=0,
                                      height=2, cursor="hand2", command=self.open_recovery_wizard)
        self.btn_recovery.pack(fill="x")
        make_hint(rec.body, "ตัวช่วยไล่กู้คืน 5 ขั้น (ข้อ 5.4) และปิดเหตุการณ์แบบ Closed-Loop").pack(anchor="w", pady=(4, 0))

    def _build_main_panel(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # ---- Incident banner + legend ----
        top = Section(parent, "📊 ภาพรวมสถานการณ์ (SITUATION OVERVIEW)", accent=COLOR_BLUE)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.card_incident = Card(top.body, accent=COLOR_SUCCESS)
        self.card_incident.pack(fill="x")
        self.lbl_incident = tk.Label(self.card_incident.body, text="✅ ไม่มีเหตุการณ์เปิดอยู่",
                                     font=("Segoe UI", 11, "bold"), fg=COLOR_GOOD, bg=COLOR_PANEL)
        self.lbl_incident.pack(anchor="w", padx=12, pady=(8, 2))
        self.lbl_incident_sub = tk.Label(self.card_incident.body, text="วันนี้: 0 เหตุการณ์",
                                         font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL)
        self.lbl_incident_sub.pack(anchor="w", padx=12, pady=(0, 8))
        legend = ("🟢 NORMAL = ปกติ   🔴 LOCKDOWN = ตัด uplink แล้ว   ⏳ นับถอยหลัง = เวลาก่อนตัดอัตโนมัติ   |   "
                  "การโจมตีทดสอบใช้ Kali ยิงจากภายนอก — โปรแกรมนี้เฝ้าระวัง+ตอบโต้เท่านั้น")
        tk.Label(top.body, text=legend, font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL,
                 justify="left", anchor="w", wraplength=660).pack(anchor="w", fill="x", pady=(8, 0))

        # ---- Log ----
        logsec = Section(parent, "📋 บันทึกเหตุการณ์เรียลไทม์ (AUDIT LOG & TELEMETRY)", accent=COLOR_ACCENT)
        logsec.grid(row=1, column=0, sticky="nsew")
        logsec.body.grid_rowconfigure(1, weight=1)
        logsec.body.grid_columnconfigure(0, weight=1)

        filt = tk.Frame(logsec.body, bg=COLOR_PANEL)
        filt.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tk.Label(filt, text="กรองระดับ:", font=FONT_HINT, fg=COLOR_MUTED, bg=COLOR_PANEL).pack(side="left")
        self.filter_var = tk.StringVar(value=FILTER_ALL)
        om = tk.OptionMenu(filt, self.filter_var, FILTER_ALL, FILTER_WARN, FILTER_CRIT,
                           command=lambda _=None: self._redraw_log())
        om.config(font=FONT_HINT, bg=COLOR_PANEL_ALT, fg=COLOR_TEXT, activebackground=COLOR_BORDER,
                  highlightthickness=0, bd=0)
        om["menu"].config(bg=COLOR_PANEL_ALT, fg=COLOR_TEXT)
        om.pack(side="left", padx=(6, 0))

        self.log_box = scrolledtext.ScrolledText(logsec.body, bg=COLOR_PANEL_ALT, fg=COLOR_TEXT,
                                                 font=FONT_MONO, bd=0, insertbackground=COLOR_TEXT,
                                                 highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        for lvl, col in LEVEL_COLORS.items():
            self.log_box.tag_config(lvl, foreground=col)
        self.log_box.insert(tk.END, "[SOC] ระบบพร้อมปฏิบัติการ...\n", "INFO")

        self.btn_verify = tk.Button(logsec.body, text="🔒  ตรวจสอบความสมบูรณ์ของ Log", font=FONT_BTN_SM,
                                    fg="white", bg=COLOR_PURPLE, activebackground=COLOR_ACCENT,
                                    command=self.verify_log_integrity, bd=0, cursor="hand2", height=1)
        self.btn_verify.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    def _build_footer(self):
        footer = tk.Frame(self.root, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))
        tk.Label(footer, text="●", font=("Segoe UI", 10), fg=COLOR_SUCCESS_HL, bg=COLOR_PANEL).pack(
            side="left", padx=(12, 4), pady=6)
        tk.Label(footer, text="HMAC-SHA256 · Nonce Anti-Replay · 30s Timestamp Window · Dead Man's Switch (60s) · ACK-tracked",
                 font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL).pack(side="left", pady=6)
        tk.Label(footer, text="AEGIS IDEA 3", font=("Segoe UI", 8, "bold"), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(side="right", padx=12, pady=6)

    # =========================================================
    # TIMERS / MONITORS
    # =========================================================
    def _tick_clock(self):
        self.lbl_clock.config(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _tick_monitors(self):
        # Dead Man's Switch: นับจาก heartbeat ที่ "ส่งสำเร็จ" ล่าสุด
        remaining = max(0, config.DEADMAN_TIMEOUT_SEC - (time.time() - self.last_heartbeat_sent_ts))
        self.lbl_deadman.config(text=f"{remaining:.0f}s")
        col = COLOR_DANGER_HL if remaining <= 10 else (COLOR_WARN_HL if remaining <= 30 else COLOR_GOOD)
        self.lbl_deadman.config(fg=col)
        self.card_deadman.set_accent(col)

        # Device liveness (ESP32 ยังส่งข้อความอยู่ไหม)
        s = self.mqtt.seconds_since_device()
        if s is None:
            self.lbl_device.config(text="⚪ ESP32: ยังไม่พบ", fg=COLOR_MUTED)
        elif s <= config.DEVICE_OFFLINE_SEC:
            self.lbl_device.config(text=f"🟢 ESP32: ออนไลน์ ({s:.0f}s)", fg=COLOR_SUCCESS_HL)
        else:
            self.lbl_device.config(text=f"🔴 ESP32: ออฟไลน์ ({s:.0f}s)", fg=COLOR_DANGER_HL)

        # ACK timeout: ส่งคำสั่งแล้วไม่มี ACK ตอบภายในเวลา
        if self.pending_cmd and (time.time() - self.pending_cmd["ts"]) > config.ACK_TIMEOUT_SEC:
            act = self.pending_cmd["action"]
            self.pending_cmd = None
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [WARN] ไม่มี ACK ตอบกลับสำหรับ {act} "
                             f"ภายใน {config.ACK_TIMEOUT_SEC}s — คำสั่งอาจไปไม่ถึงบอร์ด", db.WARN)

        self.root.after(1000, self._tick_monitors)

    def _emit_startup_warnings(self):
        for w in config.validate_config():
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [WARN] {w}", db.WARN)

    # =========================================================
    # MQTT CALLBACKS (เรียกผ่าน root.after จาก main → thread-safe)
    # =========================================================
    def set_broker_state(self, connected):
        if connected:
            self.lbl_conn.config(text="🟢 broker เชื่อมต่อ", fg=COLOR_SUCCESS_HL)
        else:
            self.lbl_conn.config(text="🔴 broker หลุด · กำลังต่อใหม่…", fg=COLOR_DANGER_HL)

    def on_status(self, state, rssi, heap):
        prev = getattr(self, "_last_uplink_state", None)   # สถานะครั้งก่อน
        changed = (prev != state)                          # เปลี่ยนไหม
        self._last_uplink_state = state

        if state == "LOCKDOWN":
            self.lbl_uplink.config(text="🔴  LOCKED DOWN", fg=COLOR_DANGER_HL)
            self.card_uplink.set_accent(COLOR_DANGER_HL)
            if changed:                                    # ← เล่นเสียงเฉพาะตอนเพิ่งเปลี่ยนเป็น LOCKDOWN
                self.trigger_alarm(config.SOUND_LOCKDOWN)
            self.refresh_incident_banner()
        else:
            self.lbl_uplink.config(text="🟢  NORMAL", fg=COLOR_ACCENT)
            self.card_uplink.set_accent(COLOR_ACCENT)
            if changed:                                    # ← เล่นเสียงเฉพาะตอนเพิ่งกลับเป็น NORMAL
                self.trigger_alarm(config.SOUND_RESTORE)
        self.lbl_rssi.config(text=f"{rssi} dBm")
        self.lbl_heap.config(text=f"{heap} B")

    def on_ack(self, ack, detail):
        """จับคู่กับคำสั่งที่รออยู่ — ยืนยันว่า ESP32 รับคำสั่งจริง"""
        if not self.pending_cmd:
            return
        act = self.pending_cmd["action"]
        if ack == "OK":
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [OK] ESP32 ยืนยันรับคำสั่ง {act} แล้ว", db.INFO)
        else:
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [WARN] ESP32 ปฏิเสธคำสั่ง {act}: {ack} ({detail})",
                             db.WARN)
        self.pending_cmd = None

    # =========================================================
    # LOG
    # =========================================================
    def log_message(self, message, level="INFO"):
        self.log_buffer.append((message, level))
        if self._passes_filter(level):
            self.log_box.insert(tk.END, f"{message}\n", level)
            self.log_box.see(tk.END)
        db.log_to_file_only(message, level)      # ← เพิ่มบรรทัดนี้: บันทึกลงไฟล์ทุกครั้ง

    def _passes_filter(self, level):
        f = self.filter_var.get() if hasattr(self, "filter_var") else FILTER_ALL
        rank = _LEVEL_RANK.get(level, 0)
        if f == FILTER_WARN:
            return rank >= 1
        if f == FILTER_CRIT:
            return rank >= 2
        return True

    def _redraw_log(self):
        self.log_box.delete("1.0", tk.END)
        for msg, lvl in self.log_buffer:
            if self._passes_filter(lvl):
                self.log_box.insert(tk.END, f"{msg}\n", lvl)
        self.log_box.see(tk.END)

    # =========================================================
    # INCIDENT BANNER
    # =========================================================
    def refresh_incident_banner(self):
        try:
            inc = db.get_open_incident()
            n = db.count_incidents_today()
            self.lbl_incident_sub.config(text=f"วันนี้: {n} เหตุการณ์")
            if inc:
                ip = inc.get("attacker_ip") or "ไม่ทราบ"
                self.lbl_incident.config(text=f"⚠️ Incident #{inc['id']} เปิดอยู่ ({inc['state']}) · IP: {ip}",
                                         fg=COLOR_WARN_HL)
                self.card_incident.set_accent(COLOR_WARN_HL)
            else:
                self.lbl_incident.config(text="✅ ไม่มีเหตุการณ์เปิดอยู่", fg=COLOR_GOOD)
                self.card_incident.set_accent(COLOR_SUCCESS)
        except Exception as e:
            print(f"banner error: {e}")

    # =========================================================
    # ARM / DISARM
    # =========================================================
    def toggle_arm(self):
        if self.locked:
            return
        pin = simpledialog.askstring("Admin Authentication",
                                     "ใส่ PIN เพื่อสลับโหมดระบบ:", show='*')
        if not config.verify_pin(pin):
            self._handle_bad_pin(pin)
            return
        self.pin_attempts = 0
        self.armed = not self.armed
        if self.armed:
            self.lbl_mode.config(text="🟢 ARMED — เฝ้าระวัง", fg=COLOR_GOOD)
            self.card_mode.set_accent(COLOR_SUCCESS)
            self.sys_section.config(highlightbackground=COLOR_BORDER)
            self.btn_arm.config(text="🔧  สลับเป็นโหมดซ่อมบำรุง (DISARM)", bg=COLOR_WARN,
                                activebackground=COLOR_WARN_HL)
            self.btn_cut.config(state="normal")
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [ARMED] เข้าสู่โหมดเฝ้าระวังปกติ", db.INFO)
            db.log_event("MODE_CHANGE", "System ARMED", db.INFO)
        else:
            self.lbl_mode.config(text="🔧 DISARMED — ซ่อมบำรุง", fg=COLOR_WARN_HL)
            self.card_mode.set_accent(COLOR_WARN_HL)
            self.btn_arm.config(text="🟢  กลับสู่โหมดเฝ้าระวัง (ARM)", bg=COLOR_SUCCESS,
                                activebackground=COLOR_SUCCESS_HL)
            self.btn_cut.config(state="disabled")
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [DISARMED] เข้าสู่โหมดซ่อมบำรุง — ปิดปุ่มตัดเน็ตชั่วคราว",
                             db.WARN)
            db.log_event("MODE_CHANGE", "System DISARMED (maintenance)", db.WARN)

    # =========================================================
    # COMMANDS
    # =========================================================
    def _handle_bad_pin(self, pin):
        if pin is None:
            return  # ยกเลิก ไม่นับเป็นกรอกผิด
        self.pin_attempts += 1
        remaining = config.MAX_PIN_ATTEMPTS - self.pin_attempts
        db.log_event("SECURITY_ALERT", f"Wrong PIN attempt ({self.pin_attempts}/{config.MAX_PIN_ATTEMPTS})",
                     db.WARN)
        if self.pin_attempts >= config.MAX_PIN_ATTEMPTS:
            self._lock_controls()
        else:
            messagebox.showerror("Access Denied", f"PIN ไม่ถูกต้อง (เหลืออีก {remaining} ครั้ง)")

    def _lock_controls(self):
        self.locked = True
        for b in (self.btn_cut, self.btn_restore, self.btn_arm, self.btn_recovery):
            b.config(state="disabled")
        self.log_message(f"[{time.strftime('%H:%M:%S')}] [CRITICAL] ใส่ PIN ผิดครบ "
                         f"{config.MAX_PIN_ATTEMPTS} ครั้ง — ล็อกการควบคุม 60 วินาที", db.CRITICAL)
        db.log_event("SECURITY_ALERT", "Controls locked (too many wrong PIN)", db.CRITICAL)
        messagebox.showerror("Locked", f"ใส่ PIN ผิดเกิน {config.MAX_PIN_ATTEMPTS} ครั้ง\nระบบล็อกการควบคุม 60 วินาที")
        self.root.after(60_000, self._unlock_controls)

    def _unlock_controls(self):
        self.locked = False
        self.pin_attempts = 0
        self.btn_restore.config(state="normal")
        self.btn_arm.config(state="normal")
        self.btn_recovery.config(state="normal")
        self.btn_cut.config(state="normal" if self.armed else "disabled")
        self.log_message(f"[{time.strftime('%H:%M:%S')}] [INFO] ปลดล็อกการควบคุมแล้ว", db.INFO)

    def _auth(self, prompt="กรุณาใส่ Admin PIN:"):
        if self.locked:
            messagebox.showwarning("Locked", "ระบบล็อกการควบคุมอยู่ กรุณารอ")
            return False
        pin = simpledialog.askstring("Admin Authentication", prompt, show='*')
        if config.verify_pin(pin):
            self.pin_attempts = 0
            return True
        self._handle_bad_pin(pin)
        return False

    def on_cut_clicked(self):
        if not self.armed:
            messagebox.showwarning("DISARMED", "ระบบอยู่ในโหมดซ่อมบำรุง — สลับเป็น ARMED ก่อนจึงจะสั่งตัดได้")
            return
        if not self._auth():
            return
        # ยืนยันซ้อน: พิมพ์ CONFIRM
        confirm = simpledialog.askstring("ยืนยันคำสั่งอันตราย",
                                         "คำสั่งนี้จะตัดการเชื่อมต่อเครือข่ายจริง\nพิมพ์ CONFIRM เพื่อยืนยัน:")
        if (confirm or "").strip().upper() != "CONFIRM":
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [INFO] ยกเลิกคำสั่งตัด (ไม่ได้ยืนยัน CONFIRM)", db.INFO)
            return
        self.prompt_block_attacker_ip()
        self.send_command("CUT_UPLINK", "ตัดการเชื่อมต่อเครือข่าย", critical=True)

    def on_restore_clicked(self):
        if not self._auth():
            return
        self.send_command("RESTORE_UPLINK", "คืนค่าระบบเครือข่ายปกติ")

    def send_command(self, action_value, desc, critical=False):
        payload, nonce = security.create_secure_payload(action_value, "cmd")
        sent = self.mqtt.publish(config.TOPIC_CMD, payload)
        t = time.strftime('%H:%M:%S')
        if sent:
            self.pending_cmd = {"action": action_value, "ts": time.time(), "nonce": nonce}
            lvl = db.CRITICAL if critical else db.INFO
            self.log_message(f"[{t}] [COMMAND] ส่ง {desc} แล้ว — รอ ACK ยืนยันจากบอร์ด", lvl)
            db.log_event("COMMAND_SENT", f"{action_value} - {desc}", lvl)
        else:
            self.log_message(f"[{t}] [WARN] ส่งคำสั่งไม่ได้ — MQTT ยังไม่เชื่อมต่อ", db.WARN)
            messagebox.showwarning("MQTT ไม่พร้อม", "ยังไม่ได้เชื่อมต่อ broker จึงส่งคำสั่งไม่ได้")

    def run_ufw_async(self, args, on_done):
        def worker():
            ok, out = comms.ufw_exec(args)
            self.root.after(0, lambda: on_done(ok, out))
        threading.Thread(target=worker, daemon=True).start()

    def prompt_block_attacker_ip(self):
        # ถ้า detector ส่ง IP มาแล้ว → ใช้เลย ไม่ต้องถาม
        auto_ip = self.mqtt.last_attacker_ip
        if auto_ip and self._is_valid_ip(auto_ip):
            ip = auto_ip
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [AUTO] ใช้ IP จาก detector: {ip}", db.WARN)
        else:
            # ไม่มี IP อัตโนมัติ → ค่อยถาม (เผื่อกรอกเอง/เว้นว่างข้าม)
            ip = simpledialog.askstring("UFW Containment",
                                        "ระบุ IP ผู้บุกรุก (เว้นว่าง = ข้าม):")
            if not ip or not ip.strip():
                self.mqtt.last_attacker_ip = None
                return
            ip = ip.strip()
            if not self._is_valid_ip(ip):
                messagebox.showerror("IP ไม่ถูกต้อง", f"'{ip}' ไม่ใช่ IP ที่ถูกต้อง")
                self.mqtt.last_attacker_ip = None
                return

        # จากตรงนี้ลงไป: มี ip ที่ถูกต้องแล้ว (ไม่ว่าจาก auto หรือกรอกเอง)
        self.mqtt.last_attacker_ip = ip
        db.create_incident(ip)
        self.refresh_incident_banner()
        t = time.strftime('%H:%M:%S')
        self.log_message(f"[{t}] [UFW] กำลังขอสิทธิ์เพื่อบล็อก {ip} ...", db.WARN)

        def on_done(ok, out):
            t2 = time.strftime('%H:%M:%S')
            if ok:
                self.log_message(f"[{t2}] [UFW] ✅ บล็อก {ip} สำเร็จ", db.WARN)
                db.log_event("UFW_BLOCK", f"deny from {ip} - success", db.WARN)
            else:
                self.log_message(f"[{t2}] [UFW] ❌ บล็อก {ip} ไม่สำเร็จ: {out}", db.WARN)
                db.log_event("UFW_BLOCK", f"deny from {ip} - failed: {out}", db.WARN)

        self.run_ufw_async(["deny", "from", ip], on_done)
    def _is_valid_ip(self, ip):
        """เช็กว่าเป็น IP address ที่ถูกต้องไหม (คืน True/False)"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False


    def on_attacker_detected(self, ip):
        """ถูกเรียกเมื่อ detector ส่ง IP ผู้โจมตีมา → ตัดเน็ตอัตโนมัติ"""
        if not self.armed:
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [AUTO] พบผู้โจมตี {ip} แต่ระบบ DISARMED — ไม่ตัด", db.WARN)
            return
        self.log_message(f"[{time.strftime('%H:%M:%S')}] [AUTO] 🚨 detector พบผู้โจมตี {ip} — ตัดเน็ตอัตโนมัติ", db.CRITICAL)
        self.mqtt.last_attacker_ip = ip
        self.send_command("CUT_UPLINK", f"ตัดอัตโนมัติจาก detector (ผู้โจมตี {ip})", critical=True)





    def handle_telegram_command(self, text):
        """สมองของ Telegram สองทาง: รับข้อความ → แยกคำสั่ง → ทำ
        ⚠️ ถูกเรียกจาก thread ของ Telegram จึงต้องเด้งกลับ main thread ด้วย root.after"""
        self.root.after(0, self._process_tg_command, text)

    def _process_tg_command(self, text):
        parts = text.split()
        if not parts:
            return
        cmd = parts[0].lower()

        if cmd in ("/status", "/hello", "/help"):
            state = "🔴 LOCKDOWN" if "LOCK" in self.lbl_uplink.cget("text") else "🟢 NORMAL"
            mode = "ARMED" if self.armed else "DISARMED"
            comms.send_telegram_reply(
                f"🛡️ AEGIS สถานะปัจจุบัน\n"
                f"Uplink: {state}\n"
                f"โหมด: {mode}\n\n"
                f"คำสั่ง:\n/status - ดูสถานะ\n/cut <PIN> - ตัดเน็ต\n/restore <PIN> - คืนค่า"
            )
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [TG] ตอบคำสั่ง {cmd}", db.INFO)

        elif cmd == "/cut":
            if not self._tg_check_pin(parts):
                return
            if not self.armed:
                comms.send_telegram_reply("⚠️ ระบบอยู่โหมด DISARMED — สลับเป็น ARMED ก่อน")
                return
            self.send_command("CUT_UPLINK", "ตัดเน็ต (สั่งผ่าน Telegram)", critical=True)
            comms.send_telegram_reply("🔴 ส่งคำสั่งตัด Uplink แล้ว — รอ ACK จากบอร์ด")
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [TG] สั่งตัดเน็ตผ่าน Telegram", db.CRITICAL)

        elif cmd == "/restore":
            if not self._tg_check_pin(parts):
                return
            self.send_command("RESTORE_UPLINK", "คืนค่า (สั่งผ่าน Telegram)")
            comms.send_telegram_reply("🟢 ส่งคำสั่งคืนค่า Uplink แล้ว — รอ ACK จากบอร์ด")
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [TG] สั่งคืนค่าผ่าน Telegram", db.INFO)
        
        else:
            comms.send_telegram_reply(f"❓ ไม่รู้จักคำสั่ง: {text}\nพิมพ์ /status ดูคำสั่งทั้งหมด")

    def _tg_check_pin(self, parts):
        """เช็ก PIN จาก Telegram + ล็อกถ้าเดาผิดหลายครั้ง"""
        # ด่านล็อก: ถ้ายังอยู่ในช่วงถูกล็อก ปฏิเสธทันที
        now = time.time()
        if now < self.tg_locked_until:
            wait = int(self.tg_locked_until - now)
            comms.send_telegram_reply(f"🔒 ถูกล็อกชั่วคราว รออีก {wait} วินาที")
            return False
        
        """เช็ก PIN ที่แนบมากับคำสั่ง Telegram เช่น /cut 1234"""
        if len(parts) < 2:
            comms.send_telegram_reply("🔒 ต้องใส่ PIN ด้วย เช่น /cut 1234")
            return False
        
        if not config.verify_pin(parts[1]):
            self.tg_pin_fails += 1
            remaining = config.MAX_PIN_ATTEMPTS - self.tg_pin_fails
            db.log_event("SECURITY_ALERT", f"Wrong PIN via Telegram ({self.tg_pin_fails})", db.WARN)
            if self.tg_pin_fails >= config.MAX_PIN_ATTEMPTS:
                self.tg_locked_until = now + 60          # ล็อก 60 วิ
                self.tg_pin_fails = 0
                comms.send_telegram_reply("🔒 ใส่ PIN ผิดหลายครั้ง — ล็อก 60 วินาที")
                self.log_message(f"[{time.strftime('%H:%M:%S')}] [TG] ล็อก Telegram (เดา PIN)", db.CRITICAL)
            else:
                comms.send_telegram_reply(f"❌ PIN ไม่ถูกต้อง (เหลืออีก {remaining} ครั้ง)")
            return False

        # PIN ถูก → รีเซ็ตตัวนับ
        self.tg_pin_fails = 0
        return True



    def verify_log_integrity(self):
        """ตรวจสอบความสมบูรณ์ของ audit log (hash chain)"""
        ok, msg = db.verify_chain()
        level = db.INFO if ok else db.CRITICAL
        self.log_message(f"[{time.strftime('%H:%M:%S')}] [VERIFY] {msg}", level)
        from tkinter import messagebox
        if ok:
            messagebox.showinfo("Log Integrity", msg)
        else:
            messagebox.showerror("⚠️ ตรวจพบการแก้ไข", msg)

    # =========================================================
    # MISC
    # =========================================================
    def trigger_alarm(self, sound_file=None):
        path = sound_file or config.SOUND_PATH
        if not os.path.exists(path):
            return

        def _play():
            for player in ("paplay", "aplay"):
                try:
                    subprocess.run([player, path], check=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue

        threading.Thread(target=_play, daemon=True).start()

    def export_audit_log(self):
        try:
            rows = db.fetch_all_logs()
            with open("aegis_security_report.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["ID", "Timestamp", "Level", "Event Type", "Details", "Incident ID"])
                w.writerows(rows)
            messagebox.showinfo("Export Success", "สร้างไฟล์ aegis_security_report.csv สำเร็จ!")
            self.log_message(f"[{time.strftime('%H:%M:%S')}] [INFO] ส่งออก Audit Log เป็น CSV แล้ว", db.INFO)
        except Exception as e:
            messagebox.showerror("Export Error", f"เกิดข้อผิดพลาด: {e}")

    def _start_background_heartbeat(self):
        def worker():
            while True:
                try:
                    payload, _ = security.create_secure_payload("alive", "hb")
                    if self.mqtt.publish(config.TOPIC_HEARTBEAT, payload):
                        self.last_heartbeat_sent_ts = time.time()
                except Exception as e:
                    print(f"[heartbeat] send failed, thread alive: {e}")
                time.sleep(config.HEARTBEAT_INTERVAL_SEC)
        threading.Thread(target=worker, daemon=True).start()

    def open_recovery_wizard(self):
        IncidentRecoveryWizard(self)
        self.refresh_incident_banner()

    def _on_close(self):
        try:
            db.log_event("SYSTEM", "SOC GUI shutting down", db.INFO)
            self.mqtt.stop()
        finally:
            self.root.destroy()


def main():
    db.init_db()
    db.log_event("SYSTEM", "SOC เริ่มทำงาน", db.INFO)   # ← เพิ่ม
    root = tk.Tk()
    mqtt = MQTTManager()
    app = AegisAdminGUI(root, mqtt)
    app.refresh_incident_banner()

    mqtt.log_callback = lambda m, l="INFO": root.after(0, app.log_message, m, l)
    mqtt.status_callback = lambda s, r, h: root.after(0, app.on_status, s, r, h)
    mqtt.connection_callback = lambda ok: root.after(0, app.set_broker_state, ok)
    mqtt.ack_callback = lambda a, d: root.after(0, app.on_ack, a, d)
    mqtt.ack_callback = lambda a, d: root.after(0, app.on_ack, a, d)
    mqtt.attacker_callback = lambda ip: root.after(0, app.on_attacker_detected, ip)   # ← เพิ่มบรรทัดนี้
    mqtt.start()

    # เพิ่ม 3 บรรทัดนี้: เริ่มตัวฟังคำสั่ง Telegram
    from .telegram_control import TelegramListener
    tg = TelegramListener(on_command=app.handle_telegram_command)
    tg.start()

    root.mainloop()
