"""
AEGIS IDEA 3 — Attack Detector
เฝ้า /var/log/auth.log จับ SSH brute-force แล้ว publish IP ผู้โจมตีเข้า MQTT
รัน: sudo python3 detector.py   (ต้อง sudo เพราะอ่าน auth.log)
"""
import os
import time
import re
import json
import hmac
import hashlib
import paho.mqtt.client as mqtt
from collections import defaultdict, deque

# ===== ตั้งค่า =====
BROKER = os.getenv("AEGIS_BROKER_IP", "127.0.0.1")
PORT = int(os.getenv("AEGIS_BROKER_PORT", "1883"))
MQTT_USER = os.getenv("AEGIS_MQTT_USER", "aegis")
MQTT_PASS = os.getenv("AEGIS_MQTT_PASS", "")     # ← ไม่มีค่า default ที่เป็นรหัสจริง                # ให้ตรงกับที่ตั้งใน broker
TOPIC_ATTACKER = "aegis/attacker_ip"
AUTH_LOG = "/var/log/auth.log"     # Arch อาจเป็น journalctl (ดูหมายเหตุด้านล่าง)

FAIL_THRESHOLD = 5                 # ล้มเหลวกี่ครั้ง
TIME_WINDOW = 30                   # ภายในกี่วินาที

# ===== เชื่อม MQTT =====
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)   # paho 2.x
except AttributeError:
    client = mqtt.Client()                                    # paho 1.x
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(BROKER, PORT, 60)
client.loop_start()

# ===== ตัวนับแบบ sliding window =====
fail_times = defaultdict(lambda: deque())   # ip -> เวลาที่ล้มเหลว
already_reported = set()                     # กัน publish ซ้ำ




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

_load_dotenv()

def report_attacker(ip):
    if ip in already_reported:
        return
    already_reported.add(ip)
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

def tail_journal():
    """อ่าน log จาก systemd journal แบบเรียลไทม์"""
    proc = subprocess.Popen(
        ["journalctl", "-f", "-n", "0", "-o", "cat", "_COMM=sshd-session"],
        stdout=subprocess.PIPE, text=True
    )
    for line in proc.stdout:
        process_line(line)

if __name__ == "__main__":
    print("[DETECTOR] เริ่มเฝ้า systemd journal (auth/sshd) ...")
    tail_journal()