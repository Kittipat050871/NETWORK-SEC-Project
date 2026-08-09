"""
AEGIS IDEA 3 — MQTT client
- ติดตามสถานะการเชื่อมต่อ broker (connection_callback)
- ติดตาม "อุปกรณ์ ESP32 ยังมีชีวิตไหม" จากเวลาที่ได้รับข้อความล่าสุด (device liveness)
- ส่งต่อ ACK ของคำสั่งให้ GUI ตรวจว่าคำสั่งถึงบอร์ดจริงหรือไม่ (ack_callback)

Callback ทั้งหมดถูกเรียกจาก thread ของ MQTT — ฝั่ง GUI ต้องห่อด้วย root.after เพื่อความปลอดภัย
"""
import json
import time

import paho.mqtt.client as mqtt

from . import config
from . import database as db


class MQTTManager:
    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.is_connected = False
        self.last_device_msg_ts = None   # เวลาที่ได้รับข้อความจาก ESP32 ล่าสุด
        self.last_attacker_ip = None

        # callbacks (ตั้งค่าโดย GUI)
        self.log_callback = None          # (message: str, level: str)
        self.status_callback = None       # (state, rssi, heap)
        self.connection_callback = None   # (connected: bool)
        self.ack_callback = None          # (ack: str, detail: str)

        self.client.on_message = self._on_message
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # ---------- connection ----------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self.is_connected = True
        client.subscribe([(config.TOPIC_ACK, 0), (config.TOPIC_STATUS, 0),
                          (config.TOPIC_ATTACKER_IP, 0)])
        db.log_event("SYSTEM", "MQTT connected", db.INFO)
        if self.connection_callback:
            self.connection_callback(True)

    def _on_disconnect(self, client, userdata, *args):
        print(">>> DISCONNECTED")   # เพิ่มบรรทัดนี้ชั่วคราว
        self.is_connected = False
        if self.connection_callback:
            self.connection_callback(False)

    # ---------- inbound ----------
    def _mark_device_seen(self):
        self.last_device_msg_ts = time.time()

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
            t = time.strftime('%H:%M:%S')

            if msg.topic == config.TOPIC_ACK:
                self._mark_device_seen()
                data = json.loads(payload_str)
                ack = data.get("ack", "")
                detail = data.get("detail", "")
                level = db.INFO if ack == "OK" else db.WARN
                self._log(f"[{t}] [ACK] {ack} | {detail}", level)
                db.log_event("ACK_RECEIVED", f"{ack} - {detail}", level)
                if self.ack_callback:
                    self.ack_callback(ack, detail)

            elif msg.topic == config.TOPIC_ATTACKER_IP:
                self._mark_device_seen()
                ip = payload_str.strip()
                if ip:
                    self.last_attacker_ip = ip
                    self._log(f"[{t}] [DETECTOR] พบ IP ต้องสงสัย: {ip}", db.WARN)

            elif msg.topic == config.TOPIC_STATUS:
                self._mark_device_seen()
                data = json.loads(payload_str)
                state = data.get("state", "NORMAL")
                reason = data.get("reason", "")
                rssi = data.get("rssi", 0)
                heap = data.get("heap", 0)
                level = db.CRITICAL if state == "LOCKDOWN" else db.INFO
                self._log(f"[{t}] [STATUS] {state} | {reason} | RSSI:{rssi}dBm | Heap:{heap}B", level)
                if self.status_callback:
                    self.status_callback(state, rssi, heap)
                db.log_event("DEVICE_STATUS", f"{state} ({reason})", level)

                if state in ("LOCKDOWN", "NORMAL"):
                    attacker_ip = self.last_attacker_ip if state == "LOCKDOWN" else None
                    # แจ้ง Telegram (import ในนี้กัน circular)
                    from . import comms
                    comms.send_webhook_alert(state, reason, rssi, heap, attacker_ip=attacker_ip)
                    if state == "LOCKDOWN":
                        self.last_attacker_ip = None
        except Exception as e:
            print(f"MQTT parse error: {e}")

    def _log(self, message, level):
        if self.log_callback:
            self.log_callback(message, level)

    # ---------- helpers ----------
    def seconds_since_device(self):
        """คืนจำนวนวินาทีตั้งแต่ได้รับข้อความจาก ESP32 ล่าสุด (None = ยังไม่เคยได้รับ)"""
        if self.last_device_msg_ts is None:
            return None
        return time.time() - self.last_device_msg_ts

    def device_online(self):
        s = self.seconds_since_device()
        return s is not None and s <= config.DEVICE_OFFLINE_SEC

    # ---------- lifecycle ----------
    def start(self):
        try:
            self.client.connect_async(config.BROKER_IP, config.PORT, 10)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] start error: {e}")

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def publish(self, topic, payload):
        if self.is_connected:
            self.client.publish(topic, payload)
            return True
        return False
