import paho.mqtt.client as mqtt
import json
import time
import hmac
import hashlib
import uuid
import threading
import sqlite3
import urllib.request
import os
import csv
import subprocess
import tkinter as tk

from tkinter import scrolledtext, simpledialog, messagebox, ttk

# ==========================================
# 1. CONFIGURATION & DATABASE SETUP
# ==========================================
BROKER_IP = "192.168.2.174"
PORT = 1883
SECRET_KEY = b"AEGIS-DEMO-SHARED-SECRET-change-me"
ADMIN_PIN = "1234"  # รหัสผ่านสำหรับปลดล็อกกดปุ่ม

# ตั้งค่า Telegram Bot
TELEGRAM_BOT_TOKEN = "8802233580:AAHFY9eJr03N8CuXIG1PkYfUNiNzX3TFsLI"
TELEGRAM_CHAT_ID = "7157064467"

TOPIC_CMD = "aegis/lockdown/cmd"
TOPIC_ACK = "aegis/lockdown/ack"
TOPIC_HEARTBEAT = "aegis/heartbeat"
TOPIC_STATUS = "aegis/status"
TOPIC_ATTACKER_IP = "aegis/attacker_ip"  # IP ผู้บุกรุก (จากแอดมินกรอกเอง หรือจาก Auto-Detector) แนบเข้า Telegram ตอน LOCKDOWN

HEARTBEAT_INTERVAL_SEC = 15
DEADMAN_TIMEOUT_SEC = 60  # ต้องตรงกับ DEADMAN_TIMEOUT_MS ใน src/main.cpp

def init_db():
    conn = sqlite3.connect("aegis_audit.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            details TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_to_db(event_type, details):
    try:
        conn = sqlite3.connect("aegis_audit.db")
        cursor = conn.cursor()
        t_str = time.strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO audit_logs (timestamp, event_type, details) VALUES (?, ?, ?)", (t_str, event_type, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
    send_ops_alert(event_type, details)

# ==========================================
# 2. SECURITY & TELEGRAM NOTIFICATION MODULE
# ==========================================
def send_webhook_alert(state, reason, rssi=None, heap=None, attacker_ip=None):
    """ส่งแจ้งเตือนเข้า Telegram แบบสองภาษา (ไทย/English) รูปแบบมืออาชีพ"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        is_lockdown = (state == "LOCKDOWN")
        ts_str = time.strftime('%d %b %Y, %H:%M:%S')

        lines = [
            "🛡️ *AEGIS IDEA 3 — SECURITY OPERATIONS CENTER*",
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            "🔴 *UPLINK LOCKDOWN TRIGGERED*" if is_lockdown else "🟢 *UPLINK RESTORED*",
            "_ระบบตัดการเชื่อมต่อ Uplink แล้ว_" if is_lockdown else "_ระบบเชื่อมต่อ Uplink กลับสู่ปกติแล้ว_",
            "",
            "*Reason / เหตุผล:*",
            f"`{reason}`",
            "",
            f"🕐 {ts_str}",
        ]
        if rssi is not None and heap is not None:
            lines.append(f"📶 RSSI: `{rssi} dBm`   💾 Heap: `{heap} B`")
        if is_lockdown and attacker_ip:
            lines.append(f"🎯 *Attacker IP:* `{attacker_ip}`")
        lines.append("")
        if is_lockdown:
            lines.append("⚠️ *EN:* Physical uplink has been cut. Admin action is required via the Management VLAN.")
            lines.append("⚠️ *TH:* ตัดสาย Uplink ทางกายภาพแล้ว กรุณาเข้าผ่าน Management VLAN เพื่อตรวจสอบและกู้คืนระบบ")
        else:
            lines.append("✅ *EN:* System is back online and operating normally.")
            lines.append("✅ *TH:* ระบบกลับมาออนไลน์และทำงานได้ตามปกติแล้ว")

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "\n".join(lines),
            "parse_mode": "Markdown"
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"Telegram Webhook error: {e}")


OPS_ALERT_LABELS = {
    "SECURITY_ALERT": ("🚨 SECURITY ALERT", "แจ้งเตือนความปลอดภัย (พยายามใช้งานโดยไม่ได้รับอนุญาต)"),
    "UFW_BLOCK": ("🧱 UFW CONTAINMENT", "การบล็อก IP ด้วย UFW"),
    "RECOVERY_STEP": ("🧯 RECOVERY PROGRESS", "ความคืบหน้าการกู้คืนระบบ"),
    "INCIDENT_CLOSED": ("✅ INCIDENT CLOSED", "ปิดเหตุการณ์ (บันทึกบทเรียนแล้ว)"),
}

def send_ops_alert(event_type, details):
    """ส่งเหตุการณ์สำคัญ (นอกเหนือจาก LOCKDOWN/RESTORED) เข้า Telegram ให้แอดมิน
    เห็นได้แม้ไม่ได้อยู่หน้าห้อง server — เก็บลง SQLite เหมือนเดิมควบคู่กัน ไม่แทนที่กัน"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    if event_type not in OPS_ALERT_LABELS:
        return

    def _send():
        try:
            title_en, title_th = OPS_ALERT_LABELS[event_type]
            ts_str = time.strftime('%d %b %Y, %H:%M:%S')
            text = (
                f"🛡️ *AEGIS IDEA 3 — SOC*\n"
                f"{title_en}\n"
                f"_{title_th}_\n\n"
                f"`{details}`\n\n"
                f"🕐 {ts_str}"
            )
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            }).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            urllib.request.urlopen(req, timeout=3)
        except Exception as e:
            print(f"Telegram Ops Alert error: {e}")

    threading.Thread(target=_send, daemon=True).start()

# ==========================================
# 2B. UFW CONTAINMENT (ตามเอกสารข้อ 5.2 ขั้น 3 — ตัดวงจรกายภาพคู่กับบล็อกซอฟต์แวร์)
# ==========================================
def ufw_exec(args, timeout=30):
    """เรียก ufw ผ่าน pkexec (ขอสิทธิ์ root แบบ popup กราฟิก ไม่ค้างรอรหัสผ่านใน terminal)
    คืนค่า (success: bool, output: str)"""
    try:
        result = subprocess.run(["pkexec", "ufw"] + args, capture_output=True, text=True, timeout=timeout)
        ok = (result.returncode == 0)
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        return ok, out
    except FileNotFoundError:
        return False, "ไม่พบ pkexec หรือ ufw บนระบบนี้"
    except subprocess.TimeoutExpired:
        return False, "หมดเวลารอการยืนยันตัวตน (ผู้ใช้ไม่กดยืนยัน popup ทันเวลา)"
    except Exception as e:
        return False, str(e)


def create_secure_payload(action_type: str, action_value: str, custom_ts=None, custom_nonce=None, bad_sig=False) -> str:
    """ฟังก์ชันสร้าง HMAC, Nonce และ Timestamp (ถูกย้ายกลับมาไว้ให้เรียกใช้งานได้ถูกต้อง)"""
    nonce = custom_nonce if custom_nonce else str(uuid.uuid4())[:8]
    ts = custom_ts if custom_ts else int(time.time())
    
    payload_string = f"{action_value}|{nonce}|{ts}".encode('utf-8')
    signature = hmac.new(SECRET_KEY, payload_string, hashlib.sha256).hexdigest()

    if bad_sig:
        signature = "deadbeef" + signature[8:]

    payload_data = {
        action_type: action_value,
        "nonce": nonce,
        "ts": ts,
        "sig": signature
    }
    return json.dumps(payload_data)

# ==========================================
# 3. MQTT CLIENT MANAGER
# ==========================================
class MQTTManager:
    def __init__(self, broker, port, log_callback=None, status_callback=None):
        # อัปเกรดเรียกใช้ Client แบบระบุ Callback API version ป้องกัน Warning
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.broker = broker
        self.port = port
        self.is_connected = False
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.last_attacker_ip = None
        self.client.on_message = self.on_message

    def on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            timestamp_str = time.strftime('%H:%M:%S')

            if msg.topic == TOPIC_ACK:
                data = json.loads(payload_str)
                log_msg = f"[{timestamp_str}] [ACK] สถานะ: {data.get('ack')} | ดีเทล: {data.get('detail')}"
                if self.log_callback:
                    self.log_callback(log_msg)
                log_to_db("ACK_RECEIVED", f"{data.get('ack')} - {data.get('detail')}")

            elif msg.topic == TOPIC_ATTACKER_IP:
                ip = payload_str.strip()
                if ip:
                    self.last_attacker_ip = ip
                    if self.log_callback:
                        self.log_callback(f"[{timestamp_str}] [DETECTOR] พบ IP ต้องสงสัย: {ip}")

            elif msg.topic == TOPIC_STATUS:
                data = json.loads(payload_str)
                state = data.get("state", "NORMAL")
                reason = data.get("reason", "")
                rssi = data.get("rssi", 0)
                heap = data.get("heap", 0)

                log_msg = f"[{timestamp_str}] [STATUS] State: {state} | Reason: {reason} | RSSI: {rssi}dBm | Heap: {heap}B"
                if self.log_callback:
                    self.log_callback(log_msg)
                if self.status_callback:
                    self.status_callback(state, rssi, heap)

                log_to_db("DEVICE_STATUS", f"{state} ({reason})")

                if state in ("LOCKDOWN", "NORMAL"):
                    attacker_ip = self.last_attacker_ip if state == "LOCKDOWN" else None
                    send_webhook_alert(state, reason, rssi, heap, attacker_ip=attacker_ip)
                    if state == "LOCKDOWN":
                        self.last_attacker_ip = None  # ใช้ครั้งเดียวต่อเหตุการณ์ ไม่ให้ค้างไปโผล่ครั้งหน้า
        except Exception as e:
            print(f"Error parsing message: {e}")

    def start(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.subscribe([(TOPIC_ACK, 0), (TOPIC_STATUS, 0), (TOPIC_ATTACKER_IP, 0)])
            self.client.loop_start()
            self.is_connected = True
            log_to_db("SYSTEM", "MQTT Connected successfully")
        except Exception as e:
            self.is_connected = False
            print(f"[MQTT Error]: {e}")

    def publish_custom(self, topic, payload):
        if self.is_connected:
            self.client.publish(topic, payload)
            return True
        return False

# ==========================================
# 4. ADVANCED GUI COMMAND CENTER (SOC)
# ==========================================
COLOR_BG        = "#0b1220"
COLOR_PANEL     = "#151f32"
COLOR_PANEL_ALT = "#0a0f1a"
COLOR_BORDER    = "#263349"
COLOR_TEXT      = "#e2e8f0"
COLOR_MUTED     = "#7c8aa5"
COLOR_ACCENT    = "#38bdf8"
COLOR_DANGER    = "#dc2626"
COLOR_DANGER_HL = "#ef4444"
COLOR_SUCCESS   = "#16a34a"
COLOR_SUCCESS_HL= "#22c55e"
COLOR_GOOD      = "#4ade80"
COLOR_WARN      = "#d97706"
COLOR_WARN_HL   = "#f59e0b"
COLOR_PURPLE    = "#c084fc"
COLOR_BLUE      = "#2563eb"
COLOR_BLUE_HL   = "#3b82f6"

FONT_TITLE   = ("Segoe UI", 15, "bold")
FONT_SUB     = ("Segoe UI", 9)
FONT_SECTION = ("Segoe UI", 10, "bold")
FONT_LABEL   = ("Segoe UI", 9, "bold")
FONT_BTN     = ("Segoe UI", 10, "bold")
FONT_BTN_SM  = ("Segoe UI", 9, "bold")
FONT_MONO    = ("Consolas", 9)


class Card(tk.Frame):
    """การ์ดพื้นหลังเข้ม มีแถบสีคาดซ้ายบอกความหมาย + ขอบบางแบบ flat"""
    def __init__(self, parent, accent=COLOR_ACCENT, **kwargs):
        super().__init__(parent, bg=COLOR_BORDER, **kwargs)
        self.inner = tk.Frame(self, bg=COLOR_PANEL)
        self.inner.pack(fill="both", expand=True, padx=(0, 1), pady=1)
        self.bar = tk.Frame(self.inner, bg=accent, width=4)
        self.bar.pack(side="left", fill="y")
        self.body = tk.Frame(self.inner, bg=COLOR_PANEL)
        self.body.pack(side="left", fill="both", expand=True)

    def set_accent(self, color):
        self.bar.config(bg=color)


class Section(tk.Frame):
    """กล่อง section มีหัวข้อคาดบน คั่นด้วยเส้นบาง ให้ความรู้สึกเป็นแผงควบคุมมืออาชีพ"""
    def __init__(self, parent, title, accent=COLOR_ACCENT, **kwargs):
        super().__init__(parent, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER,
                          highlightthickness=1, bd=0, **kwargs)
        head = tk.Frame(self, bg=COLOR_PANEL)
        head.pack(fill="x", padx=12, pady=(10, 6))
        tk.Frame(head, bg=accent, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(head, text=title, font=FONT_SECTION, fg=COLOR_TEXT, bg=COLOR_PANEL).pack(side="left")
        tk.Frame(self, bg=COLOR_BORDER, height=1).pack(fill="x")
        self.body = tk.Frame(self, bg=COLOR_PANEL)
        self.body.pack(fill="both", expand=True, padx=12, pady=10)


class AegisAdminGUI:
    def __init__(self, root, mqtt_manager):
        self.root = root
        self.mqtt = mqtt_manager

        self.root.title("AEGIS IDEA 3 — Cyber-Physical SOC Command Center")
        self.root.geometry("1180x760")
        self.root.minsize(1020, 660)
        self.root.config(bg=COLOR_BG)

        self.last_heartbeat_sent_ts = time.time()

        self._build_ui()
        self._start_background_heartbeat()
        self._tick_clock()
        self._tick_deadman()

    # ---------------------------------------------------------------
    def _build_ui(self):
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)

        self._build_header()

        sidebar = tk.Frame(self.root, bg=COLOR_BG, width=360)
        sidebar.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=(0, 8))
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        main = tk.Frame(self.root, bg=COLOR_BG)
        main.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 8))
        self._build_log_panel(main)

        self._build_footer()

    # ---------------------------------------------------------------
    def _build_header(self):
        header = tk.Frame(self.root, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=16)

        left = tk.Frame(header, bg=COLOR_PANEL)
        left.pack(side="left", fill="y", padx=16, pady=12)
        tk.Label(left, text="🛡️  AEGIS IDEA 3", font=FONT_TITLE, fg=COLOR_ACCENT, bg=COLOR_PANEL).pack(anchor="w")
        tk.Label(left, text="Cyber-Physical Lockdown · Security Operations Center", font=FONT_SUB,
                 fg=COLOR_MUTED, bg=COLOR_PANEL).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=COLOR_PANEL)
        right.pack(side="right", fill="y", padx=16, pady=12)
        self.lbl_clock = tk.Label(right, text="--:--:--", font=("Segoe UI", 16, "bold"), fg=COLOR_TEXT, bg=COLOR_PANEL)
        self.lbl_clock.pack(anchor="e")
        tk.Label(right, text=f"MQTT target: {BROKER_IP}:{PORT}", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="e")

    # ---------------------------------------------------------------
    def _build_sidebar(self, parent):
        # ---- Telemetry cards ----
        tel_section = Section(parent, "⚡ LIVE TELEMETRY", accent=COLOR_ACCENT)
        tel_section.pack(fill="x", pady=(0, 12))

        self.card_uplink = Card(tel_section.body, accent=COLOR_ACCENT)
        self.card_uplink.pack(fill="x", pady=(0, 6))
        tk.Label(self.card_uplink.body, text="UPLINK STATE", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_hardware_status = tk.Label(self.card_uplink.body, text="NORMAL", font=("Segoe UI", 14, "bold"),
                                             fg=COLOR_ACCENT, bg=COLOR_PANEL)
        self.lbl_hardware_status.pack(anchor="w", padx=12, pady=(0, 8))

        row = tk.Frame(tel_section.body, bg=COLOR_PANEL)
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
        tk.Label(self.card_heap.body, text="💾 FREE HEAP", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(anchor="w", padx=10, pady=(8, 0))
        self.lbl_heap = tk.Label(self.card_heap.body, text="-- B", font=("Segoe UI", 12, "bold"),
                                  fg=COLOR_PURPLE, bg=COLOR_PANEL)
        self.lbl_heap.pack(anchor="w", padx=10, pady=(0, 8))

        self.card_deadman = Card(tel_section.body, accent=COLOR_GOOD)
        self.card_deadman.pack(fill="x", pady=(6, 0))
        dm_head = tk.Frame(self.card_deadman.body, bg=COLOR_PANEL)
        dm_head.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(dm_head, text="🐕‍🦺 DEAD MAN'S SWITCH", font=("Segoe UI", 8), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(side="left")
        self.lbl_deadman_countdown = tk.Label(self.card_deadman.body, text="60s", font=("Segoe UI", 20, "bold"),
                                               fg=COLOR_GOOD, bg=COLOR_PANEL)
        self.lbl_deadman_countdown.pack(anchor="w", padx=12)
        self.lbl_deadman_sub = tk.Label(self.card_deadman.body,
                                         text="จนกว่าจะตัด uplink อัตโนมัติถ้าขาด heartbeat",
                                         font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL)
        self.lbl_deadman_sub.pack(anchor="w", padx=12, pady=(0, 8))

        # ---- Operational controls ----
        ctl_section = Section(parent, "🕹️ OPERATIONAL CONTROLS  ·  PIN PROTECTED", accent=COLOR_DANGER)
        ctl_section.pack(fill="x", pady=(0, 12))

        self.btn_cut = tk.Button(ctl_section.body, text="🛑  ตัดเน็ตฉุกเฉิน (CUT_UPLINK)", font=FONT_BTN,
                                  fg="white", bg=COLOR_DANGER, activebackground=COLOR_DANGER_HL,
                                  activeforeground="white", height=2, bd=0, relief="flat", cursor="hand2",
                                  command=lambda: self.verify_pin_and_execute("CUT_UPLINK", "ตัดการเชื่อมต่อเครือข่าย"))
        self.btn_cut.pack(fill="x", pady=(0, 6))

        self.btn_restore = tk.Button(ctl_section.body, text="✅  คืนค่าระบบปกติ (RESTORE_UPLINK)", font=FONT_BTN,
                                      fg="white", bg=COLOR_SUCCESS, activebackground=COLOR_SUCCESS_HL,
                                      activeforeground="white", height=2, bd=0, relief="flat", cursor="hand2",
                                      command=lambda: self.verify_pin_and_execute("RESTORE_UPLINK", "คืนค่าระบบเครือข่ายปกติ"))
        self.btn_restore.pack(fill="x")

        # ---- Incident recovery ----
        rec_section = Section(parent, "🧯 INCIDENT RECOVERY", accent=COLOR_WARN)
        rec_section.pack(fill="x", pady=(0, 12))

        tk.Label(rec_section.body, text="ไล่ทำตามลำดับ 5 ขั้นตามเอกสารข้อ 5.4 หลังเหตุการณ์สงบ",
                 font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL,
                 wraplength=310, justify="left").pack(anchor="w", pady=(0, 8))

        self.btn_recovery = tk.Button(rec_section.body, text="🧯  เปิด Incident Recovery Wizard", font=FONT_BTN,
                                       fg="white", bg=COLOR_WARN, activebackground=COLOR_WARN_HL,
                                       height=2, bd=0, relief="flat", cursor="hand2",
                                       command=self.open_recovery_wizard)
        self.btn_recovery.pack(fill="x")

        # ---- Attack simulation ----
        atk_section = Section(parent, "🧪 ATTACK SIMULATION & SECURITY TEST", accent=COLOR_WARN)
        atk_section.pack(fill="x")

        self.btn_sim_stale = tk.Button(atk_section.body, text="⚠️  Test Stale Packet (>30s)", font=FONT_BTN_SM,
                                        fg="white", bg=COLOR_WARN, activebackground=COLOR_WARN_HL,
                                        command=self.sim_stale_attack, bd=0, relief="flat", cursor="hand2",
                                        height=2)
        self.btn_sim_stale.pack(fill="x", pady=(0, 6))

        self.btn_sim_bad_hmac = tk.Button(atk_section.body, text="❌  Test Tampered Signature (HMAC)", font=FONT_BTN_SM,
                                           fg="white", bg="#b91c1c", activebackground=COLOR_DANGER_HL,
                                           command=self.sim_bad_hmac_attack, bd=0, relief="flat", cursor="hand2",
                                           height=2)
        self.btn_sim_bad_hmac.pack(fill="x")

    # ---------------------------------------------------------------
    def _build_log_panel(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        log_section = Section(parent, "📋 REAL-TIME AUDIT LOG & TELEMETRY INSPECTOR", accent=COLOR_ACCENT)
        log_section.grid(row=0, column=0, sticky="nsew")
        log_section.body.grid_rowconfigure(0, weight=1)
        log_section.body.grid_columnconfigure(0, weight=1)

        self.log_box = scrolledtext.ScrolledText(log_section.body, bg=COLOR_PANEL_ALT, fg=COLOR_ACCENT,
                                                   font=FONT_MONO, bd=0, insertbackground=COLOR_TEXT,
                                                   highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.log_box.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.log_box.insert(tk.END, "[SOC System] ฐานข้อมูล Audit Trail และระบบความปลอดภัยพร้อมปฏิบัติการ...\n")

        self.btn_export = tk.Button(log_section.body, text="📥  Export Audit Log (CSV)", font=FONT_BTN_SM,
                                     fg="white", bg=COLOR_BLUE, activebackground=COLOR_BLUE_HL,
                                     command=self.export_audit_log, bd=0, cursor="hand2", height=1)
        self.btn_export.grid(row=1, column=0, sticky="ew")

    # ---------------------------------------------------------------
    def _build_footer(self):
        footer = tk.Frame(self.root, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))

        tk.Label(footer, text="●", font=("Segoe UI", 10), fg=COLOR_SUCCESS_HL, bg=COLOR_PANEL).pack(
            side="left", padx=(12, 4), pady=6)
        tk.Label(footer, text="HMAC-SHA256 · Nonce Anti-Replay · 30s Timestamp Window · Dead Man's Switch (60s)",
                 font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL).pack(side="left", pady=6)
        tk.Label(footer, text="AEGIS IDEA 3", font=("Segoe UI", 8, "bold"), fg=COLOR_MUTED,
                 bg=COLOR_PANEL).pack(side="right", padx=12, pady=6)

    # ---------------------------------------------------------------
    def _tick_clock(self):
        self.lbl_clock.config(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _tick_deadman(self):
        """นับถอยหลังเวลาที่เหลือก่อน ESP32 จะตัด uplink เองถ้าไม่มี heartbeat ใหม่มาถึง"""
        elapsed = time.time() - self.last_heartbeat_sent_ts
        remaining = max(0, DEADMAN_TIMEOUT_SEC - elapsed)

        self.lbl_deadman_countdown.config(text=f"{remaining:.0f}s")
        if remaining <= 10:
            color = COLOR_DANGER_HL
        elif remaining <= 30:
            color = COLOR_WARN_HL
        else:
            color = COLOR_GOOD
        self.lbl_deadman_countdown.config(fg=color)
        self.card_deadman.set_accent(color)

        self.root.after(1000, self._tick_deadman)

    def log_message(self, message):
        self.log_box.insert(tk.END, f"{message}\n")
        self.log_box.see(tk.END)

    def trigger_alarm(self):
        """เล่นเสียงไซเรนเตือนภัย (เล่นผ่านคำสั่งระบบ ไม่บล็อก GUI)"""
        if not os.path.exists("Sound.wav"):
            return

        def _play():
            for player in ("paplay", "aplay"):
                try:
                    subprocess.run([player, "Sound.wav"], check=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            print("Audio error: ไม่พบโปรแกรมเล่นเสียง (paplay/aplay) บนระบบ")

        threading.Thread(target=_play, daemon=True).start()

    def export_audit_log(self):
        """ดึงข้อมูลจาก SQLite ออกมาเป็นไฟล์ CSV สำหรับ Excel"""
        try:
            conn = sqlite3.connect("aegis_audit.db")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC")
            rows = cursor.fetchall()
            
            # ใช้ utf-8-sig เพื่อให้ Excel อ่านภาษาไทยได้ไม่เพี้ยน
            with open("aegis_security_report.csv", "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Timestamp", "Event Type", "Details"]) # Header
                writer.writerows(rows)
            conn.close()
            
            messagebox.showinfo("Export Success", "สร้างไฟล์ aegis_security_report.csv สำเร็จ!\nสามารถเปิดดูประวัติใน Excel ได้ทันที")
            self.log_message("[SYSTEM] ทำการ Export ข้อมูล Audit Log เป็นไฟล์ CSV เรียบร้อย")
        except Exception as e:
            messagebox.showerror("Export Error", f"เกิดข้อผิดพลาด: {e}")

    def update_telemetry_status(self, state, rssi, heap):
        if state == "LOCKDOWN":
            self.lbl_hardware_status.config(text="🔴  LOCKED DOWN", fg=COLOR_DANGER_HL)
            self.card_uplink.set_accent(COLOR_DANGER_HL)
            self.trigger_alarm()
        else:
            self.lbl_hardware_status.config(text="🟢  NORMAL", fg=COLOR_ACCENT)
            self.card_uplink.set_accent(COLOR_ACCENT)
        self.lbl_rssi.config(text=f"{rssi} dBm")
        self.lbl_heap.config(text=f"{heap} B")

    def verify_pin_and_execute(self, action_value, desc):
        entered_pin = simpledialog.askstring("Admin Authentication", "กรุณาใส่ Admin PIN (ค่าเริ่มต้น: 1234):", show='*')
        if entered_pin == ADMIN_PIN:
            if action_value == "CUT_UPLINK":
                # ถาม IP ก่อนส่งคำสั่ง เพื่อให้ทันแนบเข้า Telegram ตอน LOCKDOWN status กลับมา
                self.prompt_block_attacker_ip()
            self.send_command(action_value, desc)
        elif entered_pin is not None:
            messagebox.showerror("Access Denied", "รหัส PIN ไม่ถูกต้อง! ปฏิเสธการออกคำสั่ง")
            log_to_db("SECURITY_ALERT", "Unauthorized button click attempt (Wrong PIN)")

    def send_command(self, action_value, desc):
        payload = create_secure_payload("cmd", action_value)
        self.mqtt.publish_custom(TOPIC_CMD, payload)
        t_str = time.strftime('%H:%M:%S')
        self.log_message(f"[{t_str}] [COMMAND SENT] {desc}")
        log_to_db("COMMAND_SENT", f"{action_value} - {desc}")

    def _run_ufw_async(self, args, on_done):
        """รันคำสั่ง ufw ผ่าน pkexec ใน background thread กันไม่ให้ GUI ค้างระหว่างรอ popup ยืนยันตัวตน"""
        def worker():
            ok, out = ufw_exec(args)
            self.root.after(0, lambda: on_done(ok, out))
        threading.Thread(target=worker, daemon=True).start()

    def prompt_block_attacker_ip(self):
        """ถาม IP ผู้บุกรุก (เว้นว่างได้) — เก็บไว้แนบใน Telegram ตอน LOCKDOWN
        และสั่ง UFW บล็อกคู่กับการตัด relay ตามเอกสารข้อ 5.2 ขั้น 3"""
        ip = simpledialog.askstring(
            "UFW Containment",
            "ระบุ IP ผู้บุกรุก (จะแนบใน Telegram + บล็อกด้วย UFW คู่กับการตัดวงจร, เว้นว่าง = ข้าม):"
        )
        if not ip or not ip.strip():
            self.mqtt.last_attacker_ip = None
            return
        ip = ip.strip()
        self.mqtt.last_attacker_ip = ip
        t_str = time.strftime('%H:%M:%S')
        self.log_message(f"[{t_str}] [UFW] กำลังขอสิทธิ์ผู้ดูแลระบบเพื่อบล็อก {ip} ...")

        def on_done(ok, out):
            t2 = time.strftime('%H:%M:%S')
            if ok:
                self.log_message(f"[{t2}] [UFW] ✅ บล็อก {ip} สำเร็จ (deny)")
                log_to_db("UFW_BLOCK", f"deny from {ip} - success")
            else:
                self.log_message(f"[{t2}] [UFW] ❌ บล็อก {ip} ไม่สำเร็จ: {out}")
                log_to_db("UFW_BLOCK", f"deny from {ip} - failed: {out}")

        self._run_ufw_async(["deny", "from", ip], on_done)

    def sim_stale_attack(self):
        old_ts = int(time.time()) - 40
        payload = create_secure_payload("cmd", "CUT_UPLINK", custom_ts=old_ts)
        self.mqtt.publish_custom(TOPIC_CMD, payload)
        t_str = time.strftime('%H:%M:%S')
        self.log_message(f"[{t_str}] [ATTACK SIM] ยิง Stale Packet (เก่าเกิน 30s) ไปยังบอร์ด...")
        log_to_db("ATTACK_SIM", "Stale Packet sent")

    def sim_bad_hmac_attack(self):
        payload = create_secure_payload("cmd", "CUT_UPLINK", bad_sig=True)
        self.mqtt.publish_custom(TOPIC_CMD, payload)
        t_str = time.strftime('%H:%M:%S')
        self.log_message(f"[{t_str}] [ATTACK SIM] ยิง Tampered Packet (ปลอมลายเซ็น HMAC)...")
        log_to_db("ATTACK_SIM", "Tampered HMAC Packet sent")
        self.trigger_alarm() # <---- เพิ่มบรรทัดนี้

    def _start_background_heartbeat(self):
        def heartbeat_worker():
            while True:
                payload = create_secure_payload("hb", "alive")
                sent = self.mqtt.publish_custom(TOPIC_HEARTBEAT, payload)
                if sent:
                    self.last_heartbeat_sent_ts = time.time()
                time.sleep(HEARTBEAT_INTERVAL_SEC)

        t = threading.Thread(target=heartbeat_worker, daemon=True)
        t.start()

    def open_recovery_wizard(self):
        IncidentRecoveryWizard(self)


# ==========================================
# 4B. INCIDENT RECOVERY WIZARD (เอกสารข้อ 5.4 — Closed-Loop Recovery)
# ==========================================
class IncidentRecoveryWizard(tk.Toplevel):
    STEP_TITLES = [
        "1. Out-of-band Access",
        "2. Block Attacker IP (UFW)",
        "3. Restore Physical Uplink",
        "4. Reopen Services (UFW)",
        "5. Lessons Learned",
    ]
    STEP_DESC = [
        "เข้าระบบผ่าน Management VLAN ที่ไม่ถูกตัด เพื่อเข้าถึง NAS นอกเส้นทางปกติ (Out-of-band)",
        "นำ IP ที่เห็นใน Telegram/Log ไปแบนถาวรใน UFW ก่อนปลดล็อกกายภาพ",
        "สั่ง MQTT (nonce ใหม่) ให้ ESP32 ต่อวงจร Uplink กลับ",
        "เปิดพอร์ต/รีโหลด UFW ให้ผู้ใช้และทีมใช้งานได้ตามปกติ",
        "สรุปเหตุการณ์กลับเข้า Log ปิดวงจร (Closed-Loop) และโยงกลับ IDEA 1",
    ]

    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui
        self.status_labels = []

        self.title("Incident Recovery — กู้คืนระบบหลังเหตุการณ์")
        self.configure(bg=COLOR_BG)
        self.geometry("640x600")
        self.minsize(600, 560)
        self.transient(gui.root)

        tk.Label(self, text="🧯 Incident Recovery Checklist", font=("Segoe UI", 13, "bold"),
                 fg=COLOR_ACCENT, bg=COLOR_BG).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(self, text="ไล่ทำตามลำดับหลังเหตุการณ์สงบ ตามเอกสารออกแบบข้อ 5.4 (Incident Recovery)",
                 font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_BG).pack(anchor="w", padx=18, pady=(0, 12))

        self._build_step(0, self._step1)
        self._build_step(1, self._step2, extra="ip_entry")
        self._build_step(2, self._step3)
        self._build_step(3, self._step4)
        self._build_step(4, self._step5, extra="lessons_text")

    def _step_frame(self, idx):
        card = Card(self, accent=COLOR_WARN)
        card.pack(fill="x", padx=18, pady=6)
        head = tk.Frame(card.body, bg=COLOR_PANEL)
        head.pack(fill="x", pady=(8, 2))
        tk.Label(head, text=self.STEP_TITLES[idx], font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT,
                 bg=COLOR_PANEL).pack(side="left", padx=12)
        status = tk.Label(head, text="⬜ Pending", font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL)
        status.pack(side="right", padx=12)
        self.status_labels.append(status)
        tk.Label(card.body, text=self.STEP_DESC[idx], font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_PANEL,
                 wraplength=560, justify="left").pack(anchor="w", padx=12)
        return card.body

    def _build_step(self, idx, command, extra=None):
        body = self._step_frame(idx)
        row = tk.Frame(body, bg=COLOR_PANEL)
        row.pack(fill="x", padx=12, pady=(6, 10))

        if extra == "ip_entry":
            self.ip_entry = tk.Entry(row, font=("Consolas", 10), width=18)
            self.ip_entry.pack(side="left")
            self.ip_entry.insert(0, "เช่น 203.0.113.42")
            tk.Button(row, text="🚫 Block Permanently", font=FONT_BTN_SM, fg="white", bg=COLOR_DANGER,
                      activebackground=COLOR_DANGER_HL, bd=0, cursor="hand2",
                      command=command).pack(side="left", padx=(8, 0))
        elif extra == "lessons_text":
            self.lessons_text = tk.Text(body, height=3, width=60, font=("Segoe UI", 9))
            self.lessons_text.pack(anchor="w", padx=12, pady=(0, 6))
            tk.Button(body, text="💾 บันทึกและปิดเหตุการณ์", font=FONT_BTN_SM, fg="white", bg=COLOR_SUCCESS,
                      activebackground=COLOR_SUCCESS_HL, bd=0, cursor="hand2",
                      command=command).pack(anchor="w", padx=12, pady=(0, 10))
        else:
            labels = {0: "✔️ ยืนยันว่าเข้าถึงผ่าน Management VLAN แล้ว",
                      2: "✅ ส่ง RESTORE_UPLINK",
                      3: "🔓 Reload UFW"}
            colors = {0: COLOR_BLUE, 2: COLOR_SUCCESS, 3: COLOR_BLUE}
            hl = {0: COLOR_BLUE_HL, 2: COLOR_SUCCESS_HL, 3: COLOR_BLUE_HL}
            tk.Button(row, text=labels[idx], font=FONT_BTN_SM, fg="white", bg=colors[idx],
                      activebackground=hl[idx], bd=0, cursor="hand2",
                      command=command).pack(anchor="w")

    def _mark_done(self, idx):
        self.status_labels[idx].config(text="✅ Done", fg=COLOR_SUCCESS_HL)

    def _log(self, text):
        t_str = time.strftime('%H:%M:%S')
        self.gui.log_message(f"[{t_str}] [RECOVERY] {text}")

    def _step1(self):
        self._mark_done(0)
        log_to_db("RECOVERY_STEP", "1. Out-of-band access confirmed (Management VLAN)")
        self._log("ขั้น 1: ยืนยันเข้าถึงผ่าน Management VLAN แล้ว")

    def _step2(self):
        ip = self.ip_entry.get().strip()
        if not ip or ip == "เช่น 203.0.113.42":
            messagebox.showwarning("ต้องระบุ IP", "กรุณาใส่ IP ที่ต้องการบล็อกก่อน", parent=self)
            return
        self._log(f"ขั้น 2: กำลังขอสิทธิ์ผู้ดูแลระบบเพื่อบล็อก {ip} ...")

        def on_done(ok, out):
            if ok:
                self._mark_done(1)
                log_to_db("RECOVERY_STEP", f"2. Blocked {ip} permanently via UFW")
                self._log(f"ขั้น 2: บล็อก {ip} สำเร็จถาวร ✅")
            else:
                self._log(f"ขั้น 2: บล็อกไม่สำเร็จ: {out}")

        self.gui._run_ufw_async(["deny", "from", ip], on_done)

    def _step3(self):
        entered_pin = simpledialog.askstring("Admin Authentication", "กรุณาใส่ Admin PIN:", show='*', parent=self)
        if entered_pin != ADMIN_PIN:
            if entered_pin is not None:
                messagebox.showerror("Access Denied", "PIN ไม่ถูกต้อง", parent=self)
            return
        payload = create_secure_payload("cmd", "RESTORE_UPLINK")
        self.gui.mqtt.publish_custom(TOPIC_CMD, payload)
        self._mark_done(2)
        log_to_db("RECOVERY_STEP", "3. Sent RESTORE_UPLINK command")
        self._log("ขั้น 3: ส่งคำสั่งปลดล็อกกายภาพแล้ว")

    def _step4(self):
        self._log("ขั้น 4: กำลังขอสิทธิ์เพื่อ reload UFW ...")

        def on_done(ok, out):
            if ok:
                self._mark_done(3)
                log_to_db("RECOVERY_STEP", "4. UFW reloaded, services reopened")
                self._log("ขั้น 4: เปิดบริการกลับคืนแล้ว ✅")
            else:
                self._log(f"ขั้น 4: ล้มเหลว: {out}")

        self.gui._run_ufw_async(["reload"], on_done)

    def _step5(self):
        summary = self.lessons_text.get("1.0", "end").strip()
        if not summary:
            messagebox.showwarning("ยังไม่ได้กรอก", "กรุณาสรุปบทเรียนก่อนปิดเหตุการณ์", parent=self)
            return
        log_to_db("INCIDENT_CLOSED", summary)
        self._mark_done(4)
        self._log("ขั้น 5: บันทึกบทเรียนแล้ว — ปิดเหตุการณ์ (Closed-Loop)")
        messagebox.showinfo("Incident Closed", "บันทึกและปิดเหตุการณ์เรียบร้อยแล้ว", parent=self)


# ==========================================
# 5. MAIN ENTRY POINT
# ==========================================
if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    
    mqtt_mgr = MQTTManager(BROKER_IP, PORT)
    app = AegisAdminGUI(root, mqtt_mgr)
    
    mqtt_mgr.log_callback = app.log_message
    mqtt_mgr.status_callback = app.update_telemetry_status
    mqtt_mgr.start()

    root.mainloop()