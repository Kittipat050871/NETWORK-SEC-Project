"""
AEGIS IDEA 3 — ชุดทดสอบอัตโนมัติ (pytest)
ทดสอบตรรกะความปลอดภัย + config โดยไม่ต้องใช้ฮาร์ดแวร์/network
รัน:  pytest -v
"""
import os
import json
import hmac
import hashlib
import tempfile

# ใช้ DB/LOG ชั่วคราว + PIN/secret สำหรับเทสต์ (ตั้งก่อน import config)
_TMP = tempfile.mkdtemp()
os.environ["AEGIS_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["AEGIS_LOG_PATH"] = os.path.join(_TMP, "test.log")
os.environ["AEGIS_ADMIN_PIN"] = "4321"
os.environ["AEGIS_HMAC_SECRET"] = "unit-test-secret"

from aegis_soc import config, security
from aegis_soc import database as db


# ---------------- Security ----------------
def _verify(payload_json):
    d = json.loads(payload_json)
    action = d.get("cmd") or d.get("hb")
    signing = f"{action}|{d['nonce']}|{d['ts']}".encode("utf-8")
    expected = hmac.new(config.SECRET_KEY, signing, hashlib.sha256).hexdigest()
    return expected == d["sig"]


def test_valid_signature_passes():
    payload, nonce = security.create_secure_payload("CUT_UPLINK", "cmd")
    assert _verify(payload) is True
    assert len(nonce) == 8


def test_tampered_payload_fails():
    payload, _ = security.create_secure_payload("CUT_UPLINK", "cmd")
    d = json.loads(payload)
    d["cmd"] = "RESTORE_UPLINK"
    assert _verify(json.dumps(d)) is False


def test_nonce_is_unique():
    nonces = {security.create_secure_payload("CUT_UPLINK")[1] for _ in range(200)}
    assert len(nonces) > 190


# ---------------- PIN ----------------
def test_pin_verify():
    assert config.verify_pin("4321") is True
    assert config.verify_pin("0000") is False
    assert config.verify_pin(None) is False


# ---------------- Incident lifecycle ----------------
def test_incident_lifecycle():
    db.init_db()
    iid = db.create_incident("203.0.113.5")
    assert iid > 0
    assert db.create_incident() == iid          # เปิดซ้ำได้ id เดิม
    db.close_incident(iid, "root cause: test")
    assert db.get_open_incident() is None


# ---------------- Config validation ----------------
def test_validate_config_returns_list():
    assert isinstance(config.validate_config(), list)


def test_invalid_ip_produces_warning():
    original = config.BROKER_IP
    config.BROKER_IP = "192.168"                 # จำลอง IP ผิด
    warnings = config.validate_config()
    config.BROKER_IP = original                  # คืนค่าเดิม (test isolation)
    assert any("IP" in w for w in warnings)