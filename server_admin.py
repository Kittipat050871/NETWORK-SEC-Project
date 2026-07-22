import paho.mqtt.client as mqtt
import json
import time
import hmac
import hashlib
import uuid
import threading
import sqlite3
import urllib.request
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox, ttk

# ==========================================
# 1. CONFIGURATION & DATABASE SETUP
# ==========================================
BROKER_IP = "192.168.1.167"
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

# ==========================================
# 2. SECURITY & TELEGRAM NOTIFICATION MODULE
# ==========================================
def send_webhook_alert(message):
    """ส่งแจ้งเตือนภัยคุกคามเข้า Telegram อัตโนมัติ"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🚨 *[AEGIS SECURITY ALERT]*\n{message}",
            "parse_mode": "Markdown"
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        print(f"Telegram Webhook error: {e}")

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
                
                if state == "LOCKDOWN":
                    send_webhook_alert(f"ระบบถูกตัดการเชื่อมต่อ! สาเหตุ: {reason}")
        except Exception as e:
            print(f"Error parsing message: {e}")

    def start(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.subscribe([(TOPIC_ACK, 0), (TOPIC_STATUS, 0)])
            self.client.loop_start()
            self.is_connected = True
            log_to_db("SYSTEM", "MQTT Connected successfully")
        except Exception as e:
            self.is_connected = False
            print(f"[MQTT Error]: {e}")

    def publish_custom(self, topic, payload):
        if self.is_connected:
            self.client.publish(topic, payload)

# ==========================================
# 4. ADVANCED GUI COMMAND CENTER (SOC)
# ==========================================
class AegisAdminGUI:
    def __init__(self, root, mqtt_manager):
        self.root = root
        self.mqtt = mqtt_manager
        
        self.root.title("AEGIS IDEA 3 - Advanced SOC & Security Operations Center")
        self.root.geometry("750x700")
        self.root.config(bg="#0f172a")
        
        self._build_ui()
        self._start_background_heartbeat()

    def _build_ui(self):
        # Header Panel
        header_frame = tk.Frame(self.root, bg="#1e293b", bd=1, relief="solid")
        header_frame.pack(pady=10, fill="x", padx=15)
        
        tk.Label(header_frame, text="🛡️ AEGIS IDEA 3 : SECURE INDUSTRIAL SOC PLATFORM", font=("Arial", 12, "bold"), fg="#38bdf8", bg="#1e293b").pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(header_frame, text="HMAC Auth, SQLite Audit, PIN Security & Live Telemetry Monitoring", font=("Arial", 9), fg="#94a3b8", bg="#1e293b").pack(anchor="w", padx=10, pady=(0, 8))

        # Status & Telemetry Grid Frame
        metrics_frame = tk.Frame(self.root, bg="#0f172a")
        metrics_frame.pack(fill="x", padx=15, pady=5)

        self.lbl_hardware_status = tk.Label(metrics_frame, text="⚡ UPLINK: NORMAL", font=("Arial", 9, "bold"), fg="#38bdf8", bg="#1e293b", padx=8, pady=6, bd=1, relief="solid")
        self.lbl_hardware_status.pack(side="left", expand=True, fill="x", padx=(0, 3))

        self.lbl_rssi = tk.Label(metrics_frame, text="📶 RSSI: -- dBm", font=("Arial", 9, "bold"), fg="#4ade80", bg="#1e293b", padx=8, pady=6, bd=1, relief="solid")
        self.lbl_rssi.pack(side="left", expand=True, fill="x", padx=3)

        self.lbl_heap = tk.Label(metrics_frame, text="💾 Heap: -- B", font=("Arial", 9, "bold"), fg="#c084fc", bg="#1e293b", padx=8, pady=6, bd=1, relief="solid")
        self.lbl_heap.pack(side="left", expand=True, fill="x", padx=(3, 0))

        # Control Panel Frame (Protected with PIN)
        control_frame = LabelFrame(self.root, text=" 🕹️ Operational Controls (PIN Protected) ", font=("Arial", 10, "bold"), fg="#e2e8f0", bg="#0f172a", bd=1, relief="solid")
        control_frame.pack(fill="x", padx=15, pady=10)

        self.btn_cut = tk.Button(control_frame, text="🛑  ตัดเน็ตฉุกเฉิน (CUT_UPLINK)", font=("Arial", 10, "bold"), fg="white", bg="#dc2626", activebackground="#ef4444", activeforeground="white",
                                 height=2, bd=0, relief="flat", cursor="hand2", command=lambda: self.verify_pin_and_execute("CUT_UPLINK", "ตัดการเชื่อมต่อเครือข่าย"))
        self.btn_cut.pack(fill="x", padx=10, pady=5)

        self.btn_restore = tk.Button(control_frame, text="✅  คืนค่าระบบปกติ (RESTORE_UPLINK)", font=("Arial", 10, "bold"), fg="white", bg="#16a34a", activebackground="#22c55e", activeforeground="white",
                                     height=2, bd=0, relief="flat", cursor="hand2", command=lambda: self.verify_pin_and_execute("RESTORE_UPLINK", "คืนค่าระบบเครือข่ายปกติ"))
        self.btn_restore.pack(fill="x", padx=10, pady=(0, 5))

        # Attack Simulation Panel
        attack_frame = LabelFrame(self.root, text=" 🧪 Attack Simulation & Security Test Panel ", font=("Arial", 10, "bold"), fg="#f43f5e", bg="#0f172a", bd=1, relief="solid")
        attack_frame.pack(fill="x", padx=15, pady=5)

        sim_sub_frame = tk.Frame(attack_frame, bg="#0f172a")
        sim_sub_frame.pack(fill="x", padx=10, pady=8)

        self.btn_sim_stale = tk.Button(sim_sub_frame, text="⚠️ Test Stale Packet (Replay)", font=("Arial", 9, "bold"), fg="white", bg="#d97706", activebackground="#f59e0b",
                                       command=self.sim_stale_attack, bd=0, relief="flat", cursor="hand2")
        self.btn_sim_stale.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.btn_sim_bad_hmac = tk.Button(sim_sub_frame, text="❌ Test Tampered Sig (HMAC)", font=("Arial", 9, "bold"), fg="white", bg="#b91c1c", activebackground="#ef4444",
                                          command=self.sim_bad_hmac_attack, bd=0, relief="flat", cursor="hand2")
        self.btn_sim_bad_hmac.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Real-time Security Log Terminal
        log_frame = LabelFrame(self.root, text=" 📋 Real-time SQLite Audit Log & Telemetry Inspector ", font=("Arial", 10, "bold"), fg="#38bdf8", bg="#0f172a", bd=1, relief="solid")
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)

        self.log_box = scrolledtext.ScrolledText(log_frame, bg="#020617", fg="#38bdf8", font=("Consolas", 9), bd=0)
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_box.insert(tk.END, "[SOC System] ฐานข้อมูล Audit Trail และระบบความปลอดภัยพร้อมปฏิบัติการ...\n")

    def log_message(self, message):
        self.log_box.insert(tk.END, f"{message}\n")
        self.log_box.see(tk.END)

    def update_telemetry_status(self, state, rssi, heap):
        if state == "LOCKDOWN":
            self.lbl_hardware_status.config(text="⚡ UPLINK: LOCKED DOWN", fg="#ef4444")
        else:
            self.lbl_hardware_status.config(text="⚡ UPLINK: NORMAL", fg="#38bdf8")
        self.lbl_rssi.config(text=f"📶 RSSI: {rssi} dBm")
        self.lbl_heap.config(text=f"💾 Heap: {heap} B")

    def verify_pin_and_execute(self, action_value, desc):
        entered_pin = simpledialog.askstring("Admin Authentication", "กรุณาใส่ Admin PIN (ค่าเริ่มต้น: 1234):", show='*')
        if entered_pin == ADMIN_PIN:
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

    def _start_background_heartbeat(self):
        def heartbeat_worker():
            while True:
                payload = create_secure_payload("hb", "alive")
                self.mqtt.publish_custom(TOPIC_HEARTBEAT, payload)
                time.sleep(15)

        t = threading.Thread(target=heartbeat_worker, daemon=True)
        t.start()

class LabelFrame(tk.LabelFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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