"""
AEGIS IDEA 3 — Attack Detector
เฝ้า /var/log/auth.log จับ SSH brute-force แล้ว publish IP ผู้โจมตีเข้า MQTT
รัน: sudo python3 detector.py   (ต้อง sudo เพราะอ่าน auth.log)
"""
import os
import re
import time
from collections import defaultdict, deque

import paho.mqtt.client as mqtt

# ===== ตั้งค่า =====
BROKER = os.getenv("AEGIS_BROKER_IP", "127.0.0.1")
PORT = int(os.getenv("AEGIS_BROKER_PORT", "1883"))
MQTT_USER = os.getenv("AEGIS_MQTT_USER", "aegis")
MQTT_PASS = os.getenv("AEGIS_MQTT_PASS", "")     # ← ไม่มีค่า default ที่เป็นรหัสจริง                # ให้ตรงกับที่ตั้งใน broker
TOPIC_ATTACKER = "aegis/attacker_ip"
AUTH_LOG = "/var/log/auth.log"     # Arch อาจเป็น journalctl (ดูหมายเหตุด้านล่าง)

FAIL_THRESHOLD = 5                 # ล้มเหลวกี่ครั้ง
TIME_WINDOW = 30                   # ภายในกี่วินาที

# ===== MQTT (ยังไม่เชื่อม — เชื่อมตอนรันจริงใน main) =====
client = None

def connect_mqtt():
    """สร้าง + เชื่อม MQTT client (เรียกเฉพาะตอนรันจริง)"""
    global client
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(BROKER, PORT, 60)
    client.loop_start()

# ===== ตัวนับแบบ sliding window =====
fail_times = defaultdict(lambda: deque())   # ip -> เวลาที่ล้มเหลว
already_reported = set()                     # กัน publish ซ้ำ

scan_ports = defaultdict(lambda: deque())   # ip -> deque ของ (เวลา, พอร์ต)
SCAN_PORT_THRESHOLD = 10                     # แตะกี่พอร์ตต่างกัน
SCAN_TIME_WINDOW = 10                        # ภายในกี่วินาที


def _load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value



def report_attacker(ip):
    if ip in already_reported:
        return
    already_reported.add(ip)
    if client is not None:              # ← เพิ่มเงื่อนไขนี้
        client.publish(TOPIC_ATTACKER, ip)
    print(f"[DETECTOR] 🚨 พบการโจมตีจาก {ip} → publish เข้า {TOPIC_ATTACKER}")

def process_line(line):
    # หา "Failed password ... from <IP>"
    m = re.search(r"Failed password.*from (\d+\.\d+\.\d+\.\d+)", line)
    if not m:
        return
    ip = m.group(1)
    now = time.time()
    dq = fail_times[ip]
    dq.append(now)
    # เอาเวลาที่เก่ากว่า window ออก
    while dq and now - dq[0] > TIME_WINDOW:
        dq.popleft()
    print(f"[DETECTOR] Failed login จาก {ip} ({len(dq)}/{FAIL_THRESHOLD})")
    if len(dq) >= FAIL_THRESHOLD:
        report_attacker(ip)

import subprocess


def process_portscan(line):
    """จับ port scan จาก log iptables (AEGIS_NEWCONN)"""
    if "AEGIS_NEWCONN" not in line:
        return
    m_ip = re.search(r"SRC=(\d+\.\d+\.\d+\.\d+)", line)
    m_port = re.search(r"DPT=(\d+)", line)
    if not m_ip or not m_port:
        return
    ip = m_ip.group(1)
    port = m_port.group(1)
    #if ip.startswith("127."):      # ข้าม localhost (กัน false alarm ตอนทดสอบ)
     #   return
    now = time.time()
    dq = scan_ports[ip]
    dq.append((now, port))
    while dq and now - dq[0][0] > SCAN_TIME_WINDOW:
        dq.popleft()
    unique_ports = {p for _, p in dq}         # นับพอร์ตไม่ซ้ำ
    print(f"[DETECTOR] Port scan? {ip} แตะ {len(unique_ports)} พอร์ต")
    if len(unique_ports) >= SCAN_PORT_THRESHOLD:
        report_attacker(ip)

def tail_journal():
    """อ่าน journal ทั้งหมด แล้วแยกว่าเป็น SSH fail หรือ port scan"""
    proc = subprocess.Popen(
        ["journalctl", "-f", "-n", "0", "-o", "cat"],
        stdout=subprocess.PIPE, text=True
    )
    for line in proc.stdout:
        process_line(line)        # จับ SSH brute-force (ของเดิม)
        process_portscan(line)    # จับ port scan (ของใหม่)

if __name__ == "__main__":
    _load_dotenv()          # ← เพิ่ม
    connect_mqtt()          # ← เพิ่ม
    print("[DETECTOR] เริ่มเฝ้า systemd journal (auth/sshd) ...")
    tail_journal()