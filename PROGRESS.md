# AEGIS IDEA 3 — สรุปความคืบหน้า

> อัปเดตล่าสุด: 24 กรกฎาคม 2569 (2026-07-24)
> Git commit ล่าสุด: `c8f91d3` (push ขึ้น GitHub แล้ว — `Kittipat050871/NETWORK-SEC-Project`, private repo)

---

## ✅ สิ่งที่ทำเสร็จแล้ว

### 1. เฟิร์มแวร์ ESP32 (`src/main.cpp`)

- [x] Build + Upload ผ่าน PlatformIO สำเร็จ (แก้ปัญหาพอร์ตผิด `ttyUSB0`→`ttyUSB1`, ปรับ `upload_speed` เป็น 115200)
- [x] แก้ปัญหา Serial Monitor ทำให้บอร์ด reset เอง (`monitor_dtr = 0`, `monitor_rts = 0`)
- [x] เพิ่มการตรวจสอบ **Timestamp Window** (`MAX_COMMAND_AGE_SEC = 30`) + sync เวลาจาก NTP ตอนบูต
- [x] เพิ่ม **HMAC ให้ Heartbeat** (เดิมไม่มีการตรวจสอบเลย ตอนนี้ต้องมี `nonce` + `ts` + `sig` เหมือนคำสั่งอื่น)
- [x] ทดสอบจริงบนฮาร์ดแวร์ครบ 5 สถานการณ์ **2 รอบ** — ผ่านทั้งหมด 5/5:

| # | สถานการณ์ | ผล |
|---|---|---|
| 1 | Valid CUT_UPLINK | ✅ `ACK: OK / uplink cut` |
| 2 | Replay Attack (nonce ซ้ำ) | ✅ `ACK: REPLAY` |
| 3 | Tamper Attack (แก้ payload หลังเซ็น) | ✅ `ACK: BAD_HMAC` |
| 4 | Stale Timestamp (เก่าเกิน 30s) | ✅ `ACK: STALE` |
| 5 | Dead Man's Switch (ขาด heartbeat 60s) | ✅ ตัดเองอัตโนมัติ |

### 2. Python SOC GUI Dashboard (`server_admin.py`)

สร้างขึ้นใหม่ทั้งหมด เป็นศูนย์ควบคุมฝั่งแอดมิน:

- [x] MQTT Manager — เชื่อมต่อ broker, ส่ง heartbeat เซ็น HMAC ทุก 15 วิ, subscribe ACK/STATUS
- [x] Admin PIN Authentication ก่อนสั่งคำสั่งที่มีผลจริง (CUT/RESTORE_UPLINK)
- [x] Attack Simulation Panel (Test Stale Packet, Test Tampered Signature)
- [x] SQLite Audit Trail (`aegis_audit.db`) + ปุ่ม Export เป็น CSV
- [x] **แก้บั๊กเสียงแจ้งเตือน** — `pygame.mixer` ใช้ไม่ได้ (ไม่มี libSDL2_mixer) เปลี่ยนไปเล่นผ่าน `paplay`/`aplay` แทน + สร้างไฟล์ `Sound.wav` เอง
- [x] **ปรับ UI เป็น Professional Dashboard** — เลย์เอาต์ 2 คอลัมน์ (header/sidebar/log panel/footer), resizable, การ์ด telemetry มีแถบสีบอกสถานะ
- [x] **Telegram Alert สองภาษา (TH/EN)** — แจ้งทั้งตอน LOCKDOWN และ RESTORED (เดิมมีแค่ LOCKDOWN) รูปแบบมืออาชีพ มีเวลา/RSSI/Heap
- [x] **Live Dead Man's Switch Countdown** — การ์ดนับถอยหลังวินาทีที่เหลือก่อนตัดอัตโนมัติ เปลี่ยนสีเขียว/เหลือง/แดงตามความเสี่ยง
- [x] **UFW Auto-Block** — ตอนกด CUT_UPLINK จะถาม IP ผู้บุกรุก แล้วสั่ง `ufw deny` ผ่าน `pkexec` (popup ขอรหัสผ่านกราฟิก) คู่กับการตัด relay ตามเอกสารข้อ 5.2
- [x] **Incident Recovery Wizard** — หน้าต่างแยก พาไล่ทำ 5 ขั้นตามเอกสารข้อ 5.4 (Out-of-band access → Block IP → Restore uplink → Reopen services → Lessons learned) log ทุกขั้นลง audit trail
- [x] **Telegram แจ้งเตือน Ops Events** — ขยายจากเดิม (แจ้งแค่ LOCKDOWN/RESTORED) ให้แจ้งเพิ่มตอน: ใส่ PIN ผิด, บล็อก/ไม่บล็อก IP สำเร็จ, ความคืบหน้า Recovery Wizard, ปิดเหตุการณ์ — เก็บ SQLite เหมือนเดิมควบคู่กัน ไม่ใช่แทนที่

### 3. เอกสาร

- [x] PDF รายงานทดสอบ v1 (ผลทดสอบฮาร์ดแวร์รอบแรก)
- [x] PDF รายงานทดสอบ v2 (อัปเดตครบทุกฟีเจอร์ที่สร้างในเซสชันนี้) — `AEGIS_IDEA3_ESP32_Test_Report.pdf`

### 4. Git / Deployment

- [x] Commit งานทั้งหมด (`c8f91d3`)
- [x] Push ขึ้น GitHub สำเร็จ (repo private ปลอดภัย)

### 5. ฮาร์ดแวร์

- [x] ยืนยันแล้วว่าอุปกรณ์ IDEA 1 ครบ (Beelink NAS, MikroTik hEX lite, TP-Link TL-SG105E)
- [x] ทดลองต่อสาย LAN จริงผ่าน relay ครั้งแรก — พบปัญหา `NO-CARRIER` ค้าง วินิจฉัยแล้วว่าเกิดจากปลายสายอีกด้านยังไม่ได้เสียบเข้าอุปกรณ์ที่มีไฟจริง (ไม่ใช่บั๊กซอฟต์แวร์ — ยืนยันด้วย ACK จาก ESP32 ว่าคำสั่งทำงานถูกต้อง)

---

## ⏳ สิ่งที่ยังไม่เสร็จ / ต้องทำต่อ

### ต้องตัดสินใจ

- [ ] **Auto-Detector** — เลือกระหว่าง (A) เปิด sshd จริงเฝ้า brute-force จริง [ไม่แนะนำ เปิดช่องโหว่จริง] หรือ (B) จำลองตัวตรวจจับแบบเดียวกับปุ่ม Test Stale/Tampered ที่มีอยู่แล้ว [แนะนำ ปลอดภัยกว่า] — **ยังไม่ได้ตัดสินใจ**

### ต้องทดสอบเอง (ทำไม่ได้แทน เพราะต้องกรอกรหัสผ่าน/PIN จริง)

- [ ] คลิกทดสอบ UFW Block/Reload ให้ครบ end-to-end (แอปเปิดค้างไว้ให้แล้ว)
- [ ] คลิกทดสอบ Incident Recovery Wizard ให้ครบทั้ง 5 ขั้น

### รอฮาร์ดแวร์/โครงสร้างเครือข่าย

- [ ] รอ Router (MikroTik) ตั้งค่ากระจายสัญญาณเสร็จ แล้วต่อสาย LAN ผ่าน relay เข้าพอร์ต **VLAN 10 (Server Zone)** ของสวิตช์ตามผังจริง (แทนที่จะต่อเข้าโน้ตบุ๊คตรงๆ แบบทดสอบเบื้องต้น)
- [ ] เช็คว่าสายที่ตัดผ่าน relay ครบคู่สาย (คู่ส้ม + คู่เขียว) หรือแค่เส้นเดียว — อาจเป็นสาเหตุที่ carrier ไม่ขึ้น
- [ ] วัดค่าไฟจริงตามระเบียบวิธี 7.8 (ต้องมี USB Power Meter)
- [ ] ปรับค่า Timeout ของ Dead Man's Switch (ปัจจุบัน 60s) ให้ตรงกับเวลาบูตจริงของ Beelink NAS (เอกสารเผื่อไว้ว่าอาจต้องขยายเป็น 90–120s)

### เอกสาร

- [ ] อัปเดตรายงานหลักโครงงาน (`AEGIS_System_Design.docx`) — เปลี่ยนสถานะ IDEA 1 จาก "ฮาร์ดแวร์ยังไม่มา" เป็น "อุปกรณ์มาครบแล้ว" และเปลี่ยนสถานะ IDEA 3 จาก "expected" เป็น "confirmed" ตามผลทดสอบจริงชุดนี้

---

## สรุปสั้นๆ

ระบบความปลอดภัยระดับ protocol (HMAC + Nonce + Timestamp + Dead Man's Switch) **ผ่านการทดสอบจริงครบ 100%** บนฮาร์ดแวร์ ยืนยันซ้ำ 2 รอบแล้ว ส่วน GUI ควบคุมสร้างเสร็จครบฟีเจอร์ตามที่ออกแบบไว้ในเอกสาร สิ่งที่เหลือหลักๆ คือ (1) ทดสอบคลิกฟีเจอร์ UFW/Wizard ให้ครบวงจรจริง (2) ตัดสินใจเรื่อง Auto-Detector (3) รอโครงสร้างเครือข่าย IDEA 1 พร้อมแล้วค่อยทดสอบตัดสายจริง
