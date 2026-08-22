"""
ทดสอบตรรกะตรวจจับของ detector.py
ไม่ต้องใช้ broker จริง — ดักจับว่า report_attacker ถูกเรียกไหม
"""
import detector


def setup_function():
    """ล้างสถานะก่อนแต่ละเทสต์ (test isolation)"""
    detector.fail_times.clear()
    detector.already_reported.clear()
    detector.scan_ports.clear()
    detector.syn_times.clear()


def test_ssh_bruteforce_triggers_after_threshold(monkeypatch):
    """Failed password เกิน 5 ครั้งจาก IP เดียว → ต้องแจ้งภัย"""
    reported = []
    monkeypatch.setattr(detector, "report_attacker", lambda ip: reported.append(ip))

    line = "Failed password for invalid user admin from 203.0.113.7 port 22 ssh2"
    for _ in range(5):
        detector.process_line(line)

    assert "203.0.113.7" in reported


def test_ssh_below_threshold_no_alert(monkeypatch):
    """Failed password แค่ 3 ครั้ง (ต่ำกว่า 5) → ยังไม่แจ้ง"""
    reported = []
    monkeypatch.setattr(detector, "report_attacker", lambda ip: reported.append(ip))

    line = "Failed password for invalid user admin from 203.0.113.8 port 22 ssh2"
    for _ in range(3):
        detector.process_line(line)

    assert reported == []


def test_normal_line_ignored(monkeypatch):
    """บรรทัด log ปกติ (ไม่ใช่ Failed password) → ไม่แจ้ง"""
    reported = []
    monkeypatch.setattr(detector, "report_attacker", lambda ip: reported.append(ip))

    detector.process_line("Accepted password for user from 10.0.0.5 port 22 ssh2")
    assert reported == []


def test_portscan_triggers_after_threshold(monkeypatch):
    """แตะพอร์ตต่างกันเกิน 10 พอร์ต → ต้องแจ้งภัย"""
    reported = []
    monkeypatch.setattr(detector, "report_attacker", lambda ip: reported.append(ip))

    for port in range(8000, 8011):    # 11 พอร์ตต่างกัน
        line = f"AEGIS_NEWCONN: SRC=203.0.113.9 DST=1.1.1.1 PROTO=TCP DPT={port}"
        detector.process_portscan(line)

    assert "203.0.113.9" in reported

def test_synflood_below_threshold_no_alert(monkeypatch):
    """SYN ต่ำกว่า threshold ภายใน window → ยังไม่แจ้งภัย"""
    reported = []

    monkeypatch.setattr(
        detector,
        "report_attacker",
        lambda ip: reported.append(ip),
    )

    line = (
        "AEGIS_NEWCONN SRC=203.0.113.10 "
        "DST=192.0.2.10 PROTO=TCP DPT=22"
    )

    for _ in range(detector.SYN_FLOOD_THRESHOLD - 1):
        detector.process_synflood(line)

    assert reported == []


def test_synflood_triggers_at_threshold(monkeypatch):
    """SYN ถึง threshold จาก IP เดียวภายใน window → ต้องแจ้งภัย"""
    reported = []

    monkeypatch.setattr(
        detector,
        "report_attacker",
        lambda ip: reported.append(ip),
    )

    line = (
        "AEGIS_NEWCONN SRC=203.0.113.11 "
        "DST=192.0.2.10 PROTO=TCP DPT=22"
    )

    for _ in range(detector.SYN_FLOOD_THRESHOLD):
        detector.process_synflood(line)

    assert "203.0.113.11" in reported