# AEGIS IDEA 3 — สรุปความคืบหน้า

> อัปเดตล่าสุด: 26 กรกฎาคม 2569 (2026-07-26)
> Git commit ล่าสุด: `d4208a0` (commit ในเครื่องแล้ว — **ยังไม่ได้ push** ขึ้น GitHub รอบนี้ ต้อง push เองผ่าน VS Code/terminal)

---

## ✅ สิ่งที่ทำเสร็จแล้ว

### 1. เฟิร์มแวร์ ESP32 (`src/main.cpp`)

- [x] Build + Upload ผ่าน PlatformIO สำเร็จ (แก้ปัญหาพอร์ตผิด, ปรับ `upload_speed` เป็น 115200)
- [x] แก้ปัญหา Serial Monitor ทำให้บอร์ด reset เอง (`monitor_dtr = 0`, `monitor_rts = 0`)
- [x] เพิ่มการตรวจสอบ **Timestamp Window** (`MAX_COMMAND_AGE_SEC = 30`) + sync เวลาจาก NTP ตอนบูต
- [x] เพิ่ม **HMAC ให้ Heartbeat** (ต้องมี `nonce` + `ts` + `sig` เหมือนคำสั่งอื่น)
- [x] ทดสอบจริงบนฮาร์ดแวร์ครบ 5 สถานการณ์ **2 รอบ** — ผ่านทั้งหมด 5/5 (Valid / Replay / Tamper / Stale / Dead Man's Switch)
- [x] **ไฟแดงกระพริบตอน Lockdown** — เดิมติดนิ่ง เปลี่ยนเป็นกระพริบทุก 300ms แบบ non-blocking (ไม่รบกวนการทำงานอื่นของ ESP32) ทดสอบจริงแล้วจังหวะพอดี

### 2. Python SOC GUI Dashboard (`server_admin.py`)

- [x] MQTT Manager, Admin PIN Authentication, Attack Simulation Panel, SQLite Audit Trail + Export CSV
- [x] แก้บั๊กเสียงแจ้งเตือน (`pygame.mixer` → `paplay`/`aplay`)
- [x] ปรับ UI เป็น Professional Dashboard (2 คอลัมน์, resizable, การ์ด telemetry)
- [x] Telegram Alert สองภาษา (TH/EN) สำหรับ LOCKDOWN/RESTORED
- [x] Live Dead Man's Switch Countdown
- [x] UFW Auto-Block (`pkexec`) + Incident Recovery Wizard (5 ขั้นตามเอกสารข้อ 5.4)
- [x] Telegram แจ้งเตือน Ops Events เพิ่มเติม (PIN ผิด, UFW block, recovery progress, ปิดเหตุการณ์) — เก็บ SQLite ควบคู่กัน ไม่แทนที่
- [x] **ทดสอบ UFW Block/Reload + Recovery Wizard จริงจนจบแล้ว** (ยืนยันจาก audit log ว่าไล่ครบ 4 ขั้น + บล็อก IP จริงผ่าน `pkexec` สำเร็จ)
- [x] **Attacker IP ใน Telegram Alert** — เพิ่ม topic `aegis/attacker_ip` ให้แอดมิน/ตัวตรวจจับแจ้ง IP ก่อนสั่ง CUT_UPLINK แล้วแนบเข้าอัตโนมัติในข้อความ LOCKDOWN (ใช้ครั้งเดียวต่อเหตุการณ์) ทดสอบส่งจริงแล้ว

### 3. Auto-Detector (`sim_auto_detector.py`)

- [x] เขียนตัวจำลอง brute-force detector (แนวทาง B ที่เลือกไว้ — จำลอง ไม่เปิด sshd จริง)
- [x] **พบ+แก้บั๊กสำคัญ:** เวอร์ชันแรกปลอมข้อความ `aegis/status` ตรงๆ (ใช้ `"sig": "fake_signature"` ซึ่ง ESP32 ปฏิเสธถูกต้อง แต่สคริปต์ดันหลอก GUI ว่าตัดสำเร็จอยู่ดี — ของปลอม 100%) แก้เป็นเซ็น HMAC จริงเหมือน `server_admin.py` ทดสอบแล้ว ESP32 ตัดวงจรจริง
- [~] **ยังเป็นสคริปต์ที่ต้องรันเอง** (manual trigger) ไม่ใช่ตัวเฝ้าระวังอัตโนมัติต่อเนื่องแบบพื้นหลัง — พิสูจน์ concept "ตรวจจับ → ส่ง IP → สั่งตัดจริง" ได้แล้ว แต่ยังไม่ใช่ daemon ที่รันเฝ้าตลอดเวลา

### 4. เอกสาร

- [x] PDF รายงานทดสอบ v1, v2 (`AEGIS_IDEA3_ESP32_Test_Report.pdf`)
- [x] ไฟล์นี้ (`PROGRESS.md`)

### 5. Git / Deployment

- [x] Commit รอบแรก (`c8f91d3`) — push ขึ้น GitHub สำเร็จ
- [x] Commit รอบสอง (`d4208a0`) — **ยังไม่ได้ push** (เครื่องนี้ไม่มี credential ให้ automation push ได้)

### 6. ฮาร์ดแวร์

- [x] ยืนยันแล้วว่าอุปกรณ์ IDEA 1 ครบ (Beelink NAS, MikroTik hEX lite, TP-Link TL-SG105E)
- [x] ทดลองต่อสาย LAN จริงผ่าน relay ครั้งแรก — พบ `NO-CARRIER` วินิจฉัยแล้วว่าเป็นเพราะปลายสายอีกด้านยังไม่ได้เสียบเข้าอุปกรณ์ที่มีไฟจริง (ซอฟต์แวร์/ESP32 ทำงานถูกต้อง ยืนยันจาก ACK)

---

## ⏳ สิ่งที่ยังไม่เสร็จ / ต้องทำต่อ

### ต้องทำทันที

- [ ] **Push commit `d4208a0` ขึ้น GitHub** (ทำเองผ่าน VS Code/terminal)
- [ ] **ยืนยันใน Telegram** ว่าเห็นบรรทัด Attacker IP จริงในข้อความ LOCKDOWN ล่าสุด

### รอฮาร์ดแวร์/โครงสร้างเครือข่าย

- [ ] รอ Router (MikroTik) ตั้งค่ากระจายสัญญาณเสร็จ แล้วต่อสาย LAN ผ่าน relay เข้าพอร์ต **VLAN 10 (Server Zone)** ของสวิตช์ตามผังจริง
- [ ] เช็คว่าสายที่ตัดผ่าน relay ครบคู่สาย (คู่ส้ม + คู่เขียว) หรือแค่เส้นเดียว
- [ ] วัดค่าไฟจริงตามระเบียบวิธี 7.8 (ต้องมี USB Power Meter)
- [ ] ปรับค่า Timeout ของ Dead Man's Switch (ปัจจุบัน 60s) ให้ตรงกับเวลาบูตจริงของ Beelink NAS

### พิจารณาต่อยอด (ไม่บังคับ)

- [ ] ทำให้ `sim_auto_detector.py` เป็น daemon เฝ้าระวังอัตโนมัติจริง (ปัจจุบันต้องรันเองทุกครั้ง) — ถ้าต้องการให้ "ตรวจจับ" เกิดขึ้นเองโดยไม่มีคนสั่ง

### เอกสาร

- [ ] อัปเดตรายงานหลักโครงงาน (`AEGIS_System_Design.docx`) — เปลี่ยนสถานะ IDEA 1 เป็น "อุปกรณ์มาครบแล้ว" และ IDEA 3 เป็น "confirmed" ตามผลทดสอบจริง

---

## สรุปสั้นๆ

ระบบความปลอดภัยระดับ protocol (HMAC + Nonce + Timestamp + Dead Man's Switch) ผ่านการทดสอบจริงครบ 100% บนฮาร์ดแวร์ ส่วน GUI ควบคุมและ Recovery Wizard ทดสอบคลิกจริงจนจบแล้ว รวมถึงแก้บั๊ก Auto-Detector ที่เคยปลอมสถานะให้เป็นของจริง และเพิ่มฟีเจอร์ไฟกระพริบ + Attacker IP ใน Telegram สิ่งที่เหลือหลักคือ push โค้ดขึ้น GitHub, รอโครงสร้างเครือข่าย IDEA 1 พร้อมค่อยทดสอบตัดสายจริง, และอัปเดตเอกสารหลักให้ตรงสถานะปัจจุบัน
