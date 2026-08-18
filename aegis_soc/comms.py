"""
AEGIS IDEA 3 — Communications
- Telegram: แจ้งเตือน LOCKDOWN/RESTORED (สองภาษา) + เหตุการณ์ปฏิบัติการ (ops)
- UFW: บล็อก IP ผู้โจมตีผ่าน pkexec
หมายเหตุ: โมดูลนี้ import แค่ config เท่านั้น เพื่อไม่ให้เกิด circular import
"""
import json
import subprocess
import threading
import time
import urllib.request

from . import config


def _post_telegram(text):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": config.TELEGRAM_CHAT_ID, "text": text,
                          "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    urllib.request.urlopen(req, timeout=3)


def send_webhook_alert(state, reason, rssi=None, heap=None, attacker_ip=None):
    """แจ้งเตือนหลักเมื่อ Uplink ถูกตัด/คืนค่า"""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        is_lockdown = (state == "LOCKDOWN")
        ts_str = time.strftime('%d %b %Y, %H:%M:%S')
        lines = [
            "🛡️ *AEGIS IDEA 3 — SECURITY OPERATIONS CENTER*",
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            "🔴 *UPLINK LOCKDOWN TRIGGERED*" if is_lockdown else "🟢 *UPLINK RESTORED*",
            "_ระบบตัดการเชื่อมต่อ Uplink แล้ว_" if is_lockdown else "_ระบบเชื่อมต่อ Uplink กลับสู่ปกติแล้ว_",
            "",
            "*Reason / เหตุผล:*",
            f"`{reason}`",
            "",
            f"🕐 {ts_str}",
        ]
        if rssi is not None and heap is not None:
            lines.append(f"📶 RSSI: `{rssi} dBm`   💾 Heap: `{heap} B`")
        if is_lockdown and attacker_ip:
            lines.append(f"🎯 *Attacker IP:* `{attacker_ip}`")
        lines.append("")
        if is_lockdown:
            lines.append("⚠️ *EN:* Physical uplink cut. Admin action required via Management VLAN.")
            lines.append("⚠️ *TH:* ตัดสาย Uplink ทางกายภาพแล้ว กรุณาเข้าผ่าน Management VLAN เพื่อตรวจสอบและกู้คืน")
        else:
            lines.append("✅ *EN:* System back online and operating normally.")
            lines.append("✅ *TH:* ระบบกลับมาออนไลน์และทำงานปกติแล้ว")
        _post_telegram("\n".join(lines))
    except Exception as e:
        print(f"Telegram Webhook error: {e}")


_OPS_LABELS = {
    "SECURITY_ALERT": ("🚨 SECURITY ALERT", "แจ้งเตือนความปลอดภัย (พยายามใช้งานโดยไม่ได้รับอนุญาต)"),
    "UFW_BLOCK": ("🧱 UFW CONTAINMENT", "การบล็อก IP ด้วย UFW"),
    "RECOVERY_STEP": ("🧯 RECOVERY PROGRESS", "ความคืบหน้าการกู้คืนระบบ"),
    "INCIDENT_CLOSED": ("✅ INCIDENT CLOSED", "ปิดเหตุการณ์ (บันทึกบทเรียนแล้ว)"),
}


def send_ops_alert(event_type, details):
    """แจ้งเหตุการณ์ปฏิบัติการเข้า Telegram (ยิงใน background thread)"""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    if event_type not in _OPS_LABELS:
        return

    def _send():
        try:
            title_en, title_th = _OPS_LABELS[event_type]
            ts_str = time.strftime('%d %b %Y, %H:%M:%S')
            _post_telegram(f"🛡️ *AEGIS IDEA 3 — SOC*\n{title_en}\n_{title_th}_\n\n"
                           f"`{details}`\n\n🕐 {ts_str}")
        except Exception as e:
            print(f"Telegram Ops Alert error: {e}")

    threading.Thread(target=_send, daemon=True).start()


def ufw_exec(args, timeout=30):
    """เรียก ufw ผ่าน pkexec — คืน (success: bool, output: str)"""
    try:
        result = subprocess.run(["pkexec", "ufw"] + args, capture_output=True,
                                text=True, timeout=timeout, check=False)
        ok = (result.returncode == 0)
        out = ((result.stdout or "") + (result.stderr or "")).strip()
        return ok, out
    except FileNotFoundError:
        return False, "ไม่พบ pkexec หรือ ufw บนระบบนี้"
    except subprocess.TimeoutExpired:
        return False, "หมดเวลารอการยืนยันตัวตน (ไม่กดยืนยัน popup ทันเวลา)"
    except Exception as e:
        return False, str(e)


def send_telegram_reply(text):
    """ส่งข้อความกลับไป Telegram (ใช้ตอบคำสั่งสองทาง)"""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        _post_telegram(text)
    except Exception as e:
        print(f"[TG] ตอบกลับไม่สำเร็จ: {e}")