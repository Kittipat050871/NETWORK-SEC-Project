"""
AEGIS IDEA 3 — Telegram สั่งงานสองทาง (ขาเข้า)
คอยฟังคำสั่งจาก Telegram แล้วสั่งระบบ — เริ่มจาก /status ก่อน (ปลอดภัย)
"""
import time
import threading
import json
import urllib.request

from . import config


class TelegramListener:
    def __init__(self, on_command):
        # on_command = ฟังก์ชันที่ GUI ส่งมาให้เรียกเวลาได้คำสั่ง
        self.on_command = on_command
        self.offset = 0
        self.running = False

    def _get_updates(self):
        """ถาม Telegram ว่ามีข้อความใหม่ไหม"""
        url = (f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
               f"/getUpdates?timeout=20&offset={self.offset}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _handle(self, msg):
        """ตรวจว่าใครส่ง + เป็นคำสั่งอะไร"""
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        # ⚠️ ด่านที่ 1: ต้องเป็น chat ของเราเท่านั้น
        if chat_id != str(config.TELEGRAM_CHAT_ID):
            print(f"[TG] ปฏิเสธข้อความจาก chat แปลกปลอม: {chat_id}")
            return

        # ส่งต่อให้ GUI ตัดสินใจ (เราจะเขียน handler ใน GUI สเต็ปถัดไป)
        self.on_command(text)

    def _loop(self):
        while self.running:
            try:
                data = self._get_updates()
                for update in data.get("result", []):
                    self.offset = update["update_id"] + 1   # เลื่อน offset กันอ่านซ้ำ
                    if "message" in update:
                        self._handle(update["message"])
            except Exception as e:
                print(f"[TG] polling error: {e}")
                time.sleep(3)

    def start(self):
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            print("[TG] ไม่มี token/chat — ข้ามการฟังคำสั่ง Telegram")
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        print("[TG] เริ่มฟังคำสั่ง Telegram แล้ว")

    def stop(self):
        self.running = False