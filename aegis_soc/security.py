"""
AEGIS IDEA 3 — Security helpers
สร้าง payload ที่เซ็น HMAC-SHA256 พร้อม Nonce + Timestamp (ใช้กับคำสั่งจริงและ heartbeat)
"""
import json
import time
import hmac
import hashlib
import uuid

from . import config


def create_secure_payload(action_value: str, action_type: str = "cmd") -> tuple[str, str]:
    """คืน (payload_json, nonce)

    action_type = "cmd" → คำสั่ง เช่น CUT_UPLINK / RESTORE_UPLINK / ARM / DISARM
    action_type = "hb"  → heartbeat (action_value = "alive")

    คืน nonce ออกมาด้วย เพื่อให้ฝั่ง GUI ผูกกับการรอ ACK ได้
    """
    nonce = str(uuid.uuid4())[:8]
    ts = int(time.time())
    signing_string = f"{action_value}|{nonce}|{ts}".encode("utf-8")
    signature = hmac.new(config.SECRET_KEY, signing_string, hashlib.sha256).hexdigest()
    payload = json.dumps({action_type: action_value, "nonce": nonce, "ts": ts, "sig": signature})
    return payload, nonce
