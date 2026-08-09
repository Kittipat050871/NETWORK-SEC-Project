"""
AEGIS IDEA 3 — Incident Recovery Wizard (เอกสารข้อ 5.4, Closed-Loop Recovery)
ผูกกับโมเดล Incident: เปิด/อัปเดตสถานะ CONTAINED และปิดเหตุการณ์เมื่อจบ 5 ขั้น
"""
import time
import tkinter as tk
from tkinter import simpledialog, messagebox

from . import config
from . import database as db
from . import security
from .theme import (Card, COLOR_BG, COLOR_PANEL, COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT,
                    COLOR_WARN, COLOR_DANGER, COLOR_DANGER_HL, COLOR_SUCCESS, COLOR_SUCCESS_HL,
                    COLOR_BLUE, COLOR_BLUE_HL, FONT_BTN_SM)


class IncidentRecoveryWizard(tk.Toplevel):
    STEP_TITLES = [
        "1. Out-of-band Access",
        "2. Block Attacker IP (UFW)",
        "3. Restore Physical Uplink",
        "4. Reopen Services (UFW)",
        "5. Lessons Learned",
    ]
    STEP_DESC = [
        "เข้าระบบผ่าน Management VLAN ที่ไม่ถูกตัด เพื่อเข้าถึง NAS นอกเส้นทางปกติ (Out-of-band)",
        "นำ IP ที่เห็นใน Telegram/Log ไปแบนถาวรใน UFW ก่อนปลดล็อกกายภาพ",
        "สั่ง MQTT (nonce ใหม่) ให้ ESP32 ต่อวงจร Uplink กลับ",
        "เปิดพอร์ต/รีโหลด UFW ให้ผู้ใช้และทีมใช้งานได้ตามปกติ",
        "สรุปเหตุการณ์กลับเข้า Log ปิดวงจร (Closed-Loop) และโยงกลับ IDEA 1",
    ]

    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui
        self.status_labels = []
        # เปิด/ดึงเหตุการณ์ที่ค้างอยู่ เพื่อผูกทุกขั้นเข้ากับ incident เดียว
        self.incident_id = db.create_incident(gui.mqtt.last_attacker_ip)

        self.title("Incident Recovery — กู้คืนระบบหลังเหตุการณ์")
        self.configure(bg=COLOR_BG)
        self.geometry("640x620")
        self.minsize(600, 560)
        self.transient(gui.root)

        tk.Label(self, text="🧯 Incident Recovery Checklist", font=("Segoe UI", 13, "bold"),
                 fg=COLOR_ACCENT, bg=COLOR_BG).pack(anchor="w", padx=18, pady=(16, 2))
        tk.Label(self, text=f"Incident #{self.incident_id} · ไล่ทำตามลำดับตามเอกสารข้อ 5.4",
                 font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_BG).pack(anchor="w", padx=18, pady=(0, 12))

        self._build_step(0, self._step1)
        self._build_step(1, self._step2, extra="ip_entry")
        self._build_step(2, self._step3)
        self._build_step(3, self._step4)
        self._build_step(4, self._step5, extra="lessons_text")

    def _step_frame(self, idx):
        card = Card(self, accent=COLOR_WARN)
        card.pack(fill="x", padx=18, pady=6)
        head = tk.Frame(card.body, bg=COLOR_PANEL)
        head.pack(fill="x", pady=(8, 2))
        tk.Label(head, text=self.STEP_TITLES[idx], font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT,
                 bg=COLOR_PANEL).pack(side="left", padx=12)
        status = tk.Label(head, text="⬜ Pending", font=("Segoe UI", 8), fg=COLOR_MUTED, bg=COLOR_PANEL)
        status.pack(side="right", padx=12)
        self.status_labels.append(status)
        tk.Label(card.body, text=self.STEP_DESC[idx], font=("Segoe UI", 9), fg=COLOR_TEXT, bg=COLOR_PANEL,
                 wraplength=560, justify="left").pack(anchor="w", padx=12)
        return card.body

    def _build_step(self, idx, command, extra=None):
        body = self._step_frame(idx)
        row = tk.Frame(body, bg=COLOR_PANEL)
        row.pack(fill="x", padx=12, pady=(6, 10))
        if extra == "ip_entry":
            self.ip_entry = tk.Entry(row, font=("Consolas", 10), width=18)
            self.ip_entry.pack(side="left")
            if self.gui.mqtt.last_attacker_ip:
                self.ip_entry.insert(0, self.gui.mqtt.last_attacker_ip)
            else:
                self.ip_entry.insert(0, "เช่น 203.0.113.42")
            tk.Button(row, text="🚫 Block Permanently", font=FONT_BTN_SM, fg="white", bg=COLOR_DANGER,
                      activebackground=COLOR_DANGER_HL, bd=0, cursor="hand2",
                      command=command).pack(side="left", padx=(8, 0))
        elif extra == "lessons_text":
            self.lessons_text = tk.Text(body, height=3, width=60, font=("Segoe UI", 9))
            self.lessons_text.pack(anchor="w", padx=12, pady=(0, 6))
            tk.Button(body, text="💾 บันทึกและปิดเหตุการณ์", font=FONT_BTN_SM, fg="white", bg=COLOR_SUCCESS,
                      activebackground=COLOR_SUCCESS_HL, bd=0, cursor="hand2",
                      command=command).pack(anchor="w", padx=12, pady=(0, 10))
        else:
            labels = {0: "✔️ ยืนยันว่าเข้าถึงผ่าน Management VLAN แล้ว",
                      2: "✅ ส่ง RESTORE_UPLINK", 3: "🔓 Reload UFW"}
            colors = {0: COLOR_BLUE, 2: COLOR_SUCCESS, 3: COLOR_BLUE}
            hl = {0: COLOR_BLUE_HL, 2: COLOR_SUCCESS_HL, 3: COLOR_BLUE_HL}
            tk.Button(row, text=labels[idx], font=FONT_BTN_SM, fg="white", bg=colors[idx],
                      activebackground=hl[idx], bd=0, cursor="hand2", command=command).pack(anchor="w")

    def _mark_done(self, idx):
        self.status_labels[idx].config(text="✅ Done", fg=COLOR_SUCCESS_HL)

    def _log(self, text, level=db.INFO):
        t = time.strftime('%H:%M:%S')
        self.gui.log_message(f"[{t}] [RECOVERY] {text}", level)

    def _step1(self):
        self._mark_done(0)
        db.set_incident_state(self.incident_id, "CONTAINED")
        db.log_event("RECOVERY_STEP", "1. Out-of-band access confirmed", db.INFO, self.incident_id)
        self._log("ขั้น 1: ยืนยันเข้าถึงผ่าน Management VLAN แล้ว")

    def _step2(self):
        ip = self.ip_entry.get().strip()
        if not ip or ip == "เช่น 203.0.113.42":
            messagebox.showwarning("ต้องระบุ IP", "กรุณาใส่ IP ที่ต้องการบล็อกก่อน", parent=self)
            return
        db.set_incident_ip(self.incident_id, ip)
        self._log(f"ขั้น 2: กำลังขอสิทธิ์ผู้ดูแลระบบเพื่อบล็อก {ip} ...", db.WARN)

        def on_done(ok, out):
            if ok:
                self._mark_done(1)
                db.log_event("RECOVERY_STEP", f"2. Blocked {ip} permanently", db.WARN, self.incident_id)
                self._log(f"ขั้น 2: บล็อก {ip} สำเร็จถาวร ✅")
            else:
                self._log(f"ขั้น 2: บล็อกไม่สำเร็จ: {out}", db.WARN)

        self.gui.run_ufw_async(["deny", "from", ip], on_done)

    def _step3(self):
        pin = simpledialog.askstring("Admin Authentication", "กรุณาใส่ Admin PIN:", show='*', parent=self)
        if not config.verify_pin(pin):
            if pin is not None:
                messagebox.showerror("Access Denied", "PIN ไม่ถูกต้อง", parent=self)
            return
        payload, _ = security.create_secure_payload("RESTORE_UPLINK", "cmd")
        self.gui.mqtt.publish(config.TOPIC_CMD, payload)
        self._mark_done(2)
        db.log_event("RECOVERY_STEP", "3. Sent RESTORE_UPLINK", db.INFO, self.incident_id)
        self._log("ขั้น 3: ส่งคำสั่งปลดล็อกกายภาพแล้ว")

    def _step4(self):
        self._log("ขั้น 4: กำลังขอสิทธิ์เพื่อ reload UFW ...")

        def on_done(ok, out):
            if ok:
                self._mark_done(3)
                db.log_event("RECOVERY_STEP", "4. UFW reloaded", db.INFO, self.incident_id)
                self._log("ขั้น 4: เปิดบริการกลับคืนแล้ว ✅")
            else:
                self._log(f"ขั้น 4: ล้มเหลว: {out}", db.WARN)

        self.gui.run_ufw_async(["reload"], on_done)

    def _step5(self):
        summary = self.lessons_text.get("1.0", "end").strip()
        if not summary:
            messagebox.showwarning("ยังไม่ได้กรอก", "กรุณาสรุปบทเรียนก่อนปิดเหตุการณ์", parent=self)
            return
        db.close_incident(self.incident_id, summary)
        db.log_event("INCIDENT_CLOSED", summary, db.INFO, self.incident_id)
        self._mark_done(4)
        self._log(f"ขั้น 5: ปิด Incident #{self.incident_id} แล้ว (Closed-Loop)")
        self.gui.refresh_incident_banner()
        messagebox.showinfo("Incident Closed", f"ปิด Incident #{self.incident_id} เรียบร้อยแล้ว", parent=self)
