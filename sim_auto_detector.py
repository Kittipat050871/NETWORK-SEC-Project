import time
import json
import hmac
import hashlib
import uuid
import paho.mqtt.client as mqtt

MQTT_BROKER = "192.168.2.174"
MQTT_PORT = 1883
MQTT_TOPIC_CMD = "aegis/lockdown/cmd"
MQTT_TOPIC_ATTACKER_IP = "aegis/attacker_ip"  # server_admin.py ฟัง topic นี้เพื่อแนบ IP เข้า Telegram ตอน LOCKDOWN
SECRET_KEY = b"AEGIS-DEMO-SHARED-SECRET-change-me"  # ต้องตรงกับ server_admin.py และ src/main.cpp
MAX_ATTEMPTS = 5
ATTACKER_IP = "103.45.67.89"


def create_secure_payload(action_type: str, action_value: str) -> str:
    """สร้าง payload พร้อม HMAC-SHA256 จริง (เหมือนที่ server_admin.py ใช้)
    เพื่อให้ ESP32 ตรวจสอบผ่านและตัดวงจรจริง แทนการปลอม status ตรงๆ แบบเดิม"""
    nonce = str(uuid.uuid4())[:8]
    ts = int(time.time())
    payload_string = f"{action_value}|{nonce}|{ts}".encode('utf-8')
    signature = hmac.new(SECRET_KEY, payload_string, hashlib.sha256).hexdigest()
    return json.dumps({action_type: action_value, "nonce": nonce, "ts": ts, "sig": signature})


def simulate_bruteforce():
    print("🛡️ [AEGIS Auto-Detector] Started monitoring SSH logs on port 22...")
    time.sleep(2)

    for i in range(1, MAX_ATTEMPTS + 1):
        print(f"⚠️ [WARNING] Failed password for root from {ATTACKER_IP} port {50000 + i} ssh2 (Attempt {i}/{MAX_ATTEMPTS})")
        time.sleep(1.5)

    print("\n🚨 [CRITICAL] Brute-force attack detected! Threshold exceeded.")
    print("💥 Triggering AEGIS LOCKDOWN Protocol...\n")
    time.sleep(1)

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        # ส่ง IP ผู้บุกรุกให้ server_admin.py รู้ก่อน จะได้ทันแนบเข้า Telegram ตอน LOCKDOWN status กลับมา
        client.publish(MQTT_TOPIC_ATTACKER_IP, ATTACKER_IP)
        print(f"📍 [MQTT] แจ้ง IP ผู้บุกรุก ({ATTACKER_IP}) ไปที่ topic: {MQTT_TOPIC_ATTACKER_IP}")
        time.sleep(0.3)

        payload = create_secure_payload("cmd", "CUT_UPLINK")
        client.publish(MQTT_TOPIC_CMD, payload)
        print(f"📡 [MQTT] ส่งคำสั่ง 'CUT_UPLINK' ที่เซ็น HMAC จริงไปที่ topic: {MQTT_TOPIC_CMD}")
        print("⏳ รอ ESP32 ตรวจสอบ HMAC แล้วตัดวงจรจริง — ดูไฟแดงที่บอร์ดหรือสถานะใน server_admin.py")

        time.sleep(1.5)
        client.disconnect()
    except Exception as e:
        print(f"❌ [ERROR] Could not connect to MQTT Broker at {MQTT_BROKER}")
        print(f"รายละเอียด Error: {e}")


if __name__ == "__main__":
    simulate_bruteforce()
