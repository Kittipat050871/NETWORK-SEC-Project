"""
AEGIS IDEA 3 — Database & structured logging
- audit_logs: บันทึกทุกเหตุการณ์ พร้อม "ระดับความรุนแรง" (severity)
- incidents: โมเดลเหตุการณ์ที่มีวงจรชีวิต (OPEN → CONTAINED → CLOSED)
- เขียน log ลงไฟล์แบบหมุนเวียน (RotatingFileHandler) ควบคู่กับ SQLite
"""
import logging
import sqlite3
import time
from logging.handlers import RotatingFileHandler

from . import comms, config

# ---- ระดับความรุนแรง ----
INFO = "INFO"
WARN = "WARN"
CRITICAL = "CRITICAL"

# เหตุการณ์ที่ให้ยิงเข้า Telegram (ops alert) ด้วย
_OPS_ALERT_EVENTS = {"SECURITY_ALERT", "UFW_BLOCK", "RECOVERY_STEP", "INCIDENT_CLOSED"}

# ---- file logger ----
_logger = logging.getLogger("aegis_soc")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _h = RotatingFileHandler(config.LOG_PATH, maxBytes=512_000, backupCount=5, encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    _logger.addHandler(_h)

_LEVEL_MAP = {INFO: logging.INFO, WARN: logging.WARNING, CRITICAL: logging.CRITICAL}


def _connect():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT DEFAULT 'INFO',
            event_type TEXT,
            details TEXT,
            incident_id INTEGER,
            hash TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at TEXT,
            closed_at TEXT,
            state TEXT DEFAULT 'OPEN',
            attacker_ip TEXT,
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()

import hashlib


def _get_last_hash():
    """ดึง hash ของแถวล่าสุด (ใช้เป็น 'แถวก่อนหน้า' ของแถวใหม่)"""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT hash FROM audit_logs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else "GENESIS"   # แถวแรกสุดใช้ค่าเริ่มต้น "GENESIS"

def _compute_hash(timestamp, level, event_type, details, prev_hash):
    """คำนวณลายนิ้วมือของแถวนี้ = hash(ข้อมูลแถวนี้ + hash แถวก่อน)"""
    data = f"{timestamp}|{level}|{event_type}|{details}|{prev_hash}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def log_event(event_type, details, level=INFO, incident_id=None):
    t_str = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        prev_hash = _get_last_hash()                                    # ← ดึง hash แถวก่อน
        row_hash = _compute_hash(t_str, level, event_type, details, prev_hash)  # ← คำนวณ hash แถวนี้
        conn = _connect()
        c = conn.cursor()
        c.execute("INSERT INTO audit_logs (timestamp, level, event_type, details, incident_id, hash) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (t_str, level, event_type, details, incident_id, row_hash))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

    _logger.log(_LEVEL_MAP.get(level, logging.INFO), f"[{event_type}] {details}")
    if event_type in _OPS_ALERT_EVENTS:
        comms.send_ops_alert(event_type, details)

def verify_chain():
    """ตรวจสอบความสมบูรณ์ของ hash chain ทั้งหมด
    คืน (is_valid, message) — ถ้าถูกแก้จะบอกว่าแถวไหน"""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, level, event_type, details, hash "
              "FROM audit_logs ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()

    prev_hash = "GENESIS"
    for row in rows:
        rid, ts, level, etype, details, stored_hash = row
        # คำนวณ hash ใหม่จากข้อมูลแถวนี้ + hash แถวก่อน
        expected = _compute_hash(ts, level, etype, details, prev_hash)
        if expected != stored_hash:
            return (False, f"⚠️ พบการแก้ไขที่แถว id={rid} ({etype}) — hash ไม่ตรง")
        prev_hash = stored_hash   # เลื่อนไปเป็นข้อต่อของแถวถัดไป

    return (True, f"✅ ตรวจสอบ {len(rows)} รายการ — ลูกโซ่สมบูรณ์ ไม่มีการแก้ไข")

def log_to_file_only(message, level=INFO):
    """เขียนลงไฟล์ log อย่างเดียว (ไม่แตะ DB) — ใช้กับข้อความที่ขึ้นจอทุกบรรทัด"""
    _logger.log(_LEVEL_MAP.get(level, logging.INFO), message)


# ---------------- Incident lifecycle ----------------
def create_incident(attacker_ip=None):
    """เปิดเหตุการณ์ใหม่ คืน incident_id (ถ้ามีเหตุการณ์เปิดค้างอยู่แล้ว คืนอันนั้นแทน)"""
    existing = get_open_incident()
    if existing:
        if attacker_ip and not existing.get("attacker_ip"):
            set_incident_ip(existing["id"], attacker_ip)
        return existing["id"]
    t_str = time.strftime('%Y-%m-%d %H:%M:%S')
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT INTO incidents (opened_at, state, attacker_ip) VALUES (?, 'OPEN', ?)",
              (t_str, attacker_ip))
    iid = c.lastrowid
    conn.commit()
    conn.close()
    return iid


def get_open_incident():
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT id, opened_at, state, attacker_ip FROM incidents "
              "WHERE state != 'CLOSED' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "opened_at": row[1], "state": row[2], "attacker_ip": row[3]}


def set_incident_state(incident_id, state):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE incidents SET state=? WHERE id=?", (state, incident_id))
    conn.commit()
    conn.close()


def set_incident_ip(incident_id, ip):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE incidents SET attacker_ip=? WHERE id=?", (ip, incident_id))
    conn.commit()
    conn.close()


def close_incident(incident_id, summary):
    t_str = time.strftime('%Y-%m-%d %H:%M:%S')
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE incidents SET state='CLOSED', closed_at=?, summary=? WHERE id=?",
              (t_str, summary, incident_id))
    conn.commit()
    conn.close()


def count_incidents_today():
    today = time.strftime('%Y-%m-%d')
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM incidents WHERE opened_at LIKE ?", (today + '%',))
    n = c.fetchone()[0]
    conn.close()
    return n


def fetch_all_logs():
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT id, timestamp, level, event_type, details, incident_id "
              "FROM audit_logs ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows
