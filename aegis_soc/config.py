"""
AEGIS IDEA 3 — Configuration
รวมค่าตั้งทั้งหมดไว้ที่เดียว อ่านจาก environment variable ก่อน (กัน secret หลุดขึ้น GitHub)
"""
import os
import hashlib


def _load_dotenv(path=".env"):
    """โหลดค่าจากไฟล์ .env เข้า environment ก่อนอ่านค่าทั้งหมด"""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"[.env] อ่านไฟล์ไม่สำเร็จ: {e}")


_load_dotenv()      # ← บรรทัดนี้สำคัญสุด: เรียกใช้ก่อนอ่านค่า

# ---- MQTT Broker ----
BROKER_IP = os.getenv("AEGIS_BROKER_IP", "192.168.2.174")
PORT = int(os.getenv("AEGIS_BROKER_PORT", "1883"))

# ---- Secrets (ตั้งผ่าน environment variable) ----
# ต้องตรงกับ HMAC_SECRET ใน src/main.cpp ของ ESP32 เสมอ
SECRET_KEY = os.getenv("AEGIS_HMAC_SECRET", "AEGIS-DEMO-SHARED-SECRET-change-me").encode("utf-8")
_ADMIN_PIN = os.getenv("AEGIS_ADMIN_PIN", "1234")
# เก็บ PIN เป็น hash ไม่เก็บ plaintext
ADMIN_PIN_HASH = hashlib.sha256(_ADMIN_PIN.encode("utf-8")).hexdigest()
MAX_PIN_ATTEMPTS = int(os.getenv("AEGIS_MAX_PIN_ATTEMPTS", "5"))

TELEGRAM_BOT_TOKEN = os.getenv("AEGIS_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("AEGIS_TG_CHAT", "")

# ---- MQTT Topics ----
TOPIC_CMD = "aegis/lockdown/cmd"
TOPIC_ACK = "aegis/lockdown/ack"
TOPIC_HEARTBEAT = "aegis/heartbeat"
TOPIC_STATUS = "aegis/status"
TOPIC_ATTACKER_IP = "aegis/attacker_ip"

# ---- Timing (วินาที) ----
HEARTBEAT_INTERVAL_SEC = 15
DEADMAN_TIMEOUT_SEC = 60          # ต้องตรงกับ DEADMAN_TIMEOUT_MS ใน src/main.cpp
ACK_TIMEOUT_SEC = 8               # ส่งคำสั่งแล้วรอ ACK ภายในกี่วินาที ก่อนเตือน
DEVICE_OFFLINE_SEC = 45           # ไม่ได้รับข้อความจาก ESP32 นานเกินนี้ = ถือว่าออฟไลน์

# ---- Files ----
DB_PATH = os.getenv("AEGIS_DB_PATH", "aegis_audit.db")
LOG_PATH = os.getenv("AEGIS_LOG_PATH", "aegis_soc.log")
SOUND_PATH = os.getenv("AEGIS_SOUND_PATH", "Sound.wav")


def validate_config():
    """ตรวจค่าตั้งตอนเริ่มโปรแกรม — คืน list ของคำเตือน (ไม่ถึงกับ error แต่ควรรู้)"""
    warnings = []
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        warnings.append("ยังไม่ได้ตั้ง AEGIS_TG_TOKEN / AEGIS_TG_CHAT — ระบบจะไม่ส่งแจ้งเตือน Telegram")
    if SECRET_KEY == b"AEGIS-DEMO-SHARED-SECRET-change-me":
        warnings.append("ใช้ HMAC secret ค่า default — ควรตั้ง AEGIS_HMAC_SECRET ให้ตรงกับ ESP32 ก่อนใช้งานจริง")
    if _ADMIN_PIN == "1234":
        warnings.append("ใช้ Admin PIN ค่า default (1234) — ควรตั้ง AEGIS_ADMIN_PIN ก่อนใช้งานจริง")
    return warnings


def verify_pin(entered_pin: str) -> bool:
    """ตรวจ PIN โดยเทียบกับ hash (ไม่มี plaintext ในหน่วยความจำ)"""
    if entered_pin is None:
        return False
    return hashlib.sha256(entered_pin.encode("utf-8")).hexdigest() == ADMIN_PIN_HASH
