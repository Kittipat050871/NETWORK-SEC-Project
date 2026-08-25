# AEGIS IDEA 3 — สรุปความคืบหน้า

> อัปเดตล่าสุด: 25 สิงหาคม 2569 (2026-08-25)
>
> Current canonical version: `v1.5-audit-race-fix`
>
> Current `main`: `a6d5630`
>
> Automated validation:
> - `pytest` = **14/14 PASS**
> - `ruff check .` = **PASS**
> - ESP32 PlatformIO firmware build = **PASS**
>
> หลักการบันทึกสถานะ:
> - ระบุว่า **PASS / Confirmed** เฉพาะสิ่งที่ทดสอบจริงแล้ว
> - แยกผล **Standalone/Lab Validation** ออกจาก **Production/VLAN/IDEA1/IDEA2 Integration**
> - ไม่แก้ไขผลการทดสอบย้อนหลังให้ดูสมบูรณ์ หากพบข้อบกพร่องให้เก็บเป็นหลักฐานและบันทึก Root Cause ตามจริง
> - Secret เช่น `.env` และ `src/secrets.h` ต้องไม่ถูก Track/Push ขึ้น GitHub

---

# 1. ภาพรวมสถานะปัจจุบัน

AEGIS IDEA 3 — Cyber-Physical Lockdown เป็นระบบ Active Defense สำหรับตรวจจับและตอบโต้ภัยคุกคามทางไซเบอร์ โดยมีเป้าหมายหลักคือ:

```text
Attack / Suspicious Activity
        ↓
Attack Detector
        ↓
MQTT attacker_ip
        ↓
SOC Command Center
        ↓
Secure CUT_UPLINK Command
        ↓
ESP32
        ↓
Relay Physical Lockdown
        ↓
ACK / Audit / Alert
        ↓
Explicit Recovery
```

ณ เวอร์ชัน `v1.5-audit-race-fix` แกนหลักของระบบ Standalone/Lab ได้รับการพัฒนาและทดสอบจริงแล้วเกือบครบทั้งหมด

สิ่งที่ยังเหลือใน Standalone หลัก ๆ คือ:

- วัดพลังงานจริงด้วย USB Power Meter

ส่วนงาน VLAN, IDEA 1, IDEA 2, MQTT TLS, systemd/watchdog และ Physical WAN Integration ถูกจัดเป็น **Production Integration Phase**

---

# 2. Current Milestones

- [x] `v1.0-standalone`
  - สร้าง baseline standalone
  - แยก Detector ให้ import/test ได้
  - เพิ่ม automated tests
  - ตั้งค่า Ruff/Lint baseline

- [x] `v1.1-pentested`
  - Kali/Lab validation
  - SSH brute-force / Port Scan
  - Explicit Recovery
  - แก้ `.env` load-order
  - Dead Man's Switch validation

- [x] `v1.2-syn-flood`
  - เพิ่ม SYN Flood / high-rate TCP event detector
  - เพิ่ม automated tests สำหรับ SYN Flood
  - Merge เข้า `main`

- [x] `v1.3-ms-latency`
  - เพิ่ม millisecond latency instrumentation
  - เก็บ runtime measurement จริง 5 รอบ
  - Software Response Latency เฉลี่ย **1.4 ms**

- [x] `v1.4-secure-boot`
  - เพิ่ม Secure Boot Grace Period 90 วินาที
  - Boot แล้วไม่มี Heartbeat → Fail-Secure Lockdown
  - Hardware validation ผ่าน

- [x] `v1.5-audit-race-fix`
  - ตรวจพบ concurrent-write race ใน Tamper-Evident Audit Log
  - ระบุ Root Cause
  - แก้ writer ให้ atomic/thread-safe
  - เพิ่ม concurrency regression test
  - เปิด Active Ledger ใหม่หลัง fix
  - Runtime validation ผ่าน

---

# 3. เฟิร์มแวร์ ESP32 (`src/main.cpp`)

## 3.1 Hardware Control

- [x] Build + Upload ผ่าน PlatformIO
- [x] ESP32 เชื่อม Wi-Fi ได้จริง
- [x] ESP32 Sync เวลาจาก NTP ได้จริง
- [x] MQTT connect / subscribe ได้จริง
- [x] Relay CUT / RESTORE ทำงานจริง
- [x] Relay มี physical actuation / เสียงคลิกจริง
- [x] LED GREEN แสดงสถานะ NORMAL
- [x] LED RED แสดงสถานะ LOCKDOWN
- [x] LED RED กระพริบแบบ non-blocking ทุกประมาณ 300 ms ระหว่าง Lockdown

ค่าฮาร์ดแวร์หลัก:

```text
RELAY_IN  = GPIO 27
LED_GREEN = GPIO 32
LED_RED   = GPIO 33

RELAY_RELEASE = HIGH
RELAY_TRIGGER = LOW
```

---

## 3.2 Secure Command Protocol

ระบบตรวจสอบคำสั่งด้วย:

- [x] HMAC-SHA256
- [x] Nonce Anti-Replay
- [x] Timestamp Window
- [x] ACK Tracking

ค่าหลัก:

```text
NONCE_HISTORY_SIZE   = 20
MAX_COMMAND_AGE_SEC  = 30
```

ทดสอบกรณี:

```text
Valid Command   → PASS
Replay          → REJECT
Tampered HMAC   → REJECT
Stale Timestamp → REJECT
```

---

# 4. Dead Man's Switch

Dead Man's Switch เดิม:

```text
SOC ส่ง Heartbeat
        ↓
ESP32 บันทึก lastHeartbeatMs
        ↓
Heartbeat หาย > 60s
        ↓
LOCKDOWN
```

ค่าปัจจุบัน:

```text
DEADMAN_TIMEOUT_MS = 60000
```

สถานะ:

- [x] ทดสอบจริงบนฮาร์ดแวร์
- [x] Broker disconnect ไม่ทำให้ `checkDeadman()` หยุดทำงาน
- [x] MQTT reconnect เปลี่ยนเป็น non-blocking
- [x] ขาด Heartbeat เกิน 60 วินาที → Relay Lockdown จริง
- [x] LED RED กระพริบ
- [x] Relay actuate จริง

---

# 5. Explicit Recovery

เดิมมีความเสี่ยงว่าหลัง Heartbeat กลับมา ระบบอาจถูกตีความว่าควรกลับ NORMAL

ปัจจุบันใช้ **Explicit Recovery**

```text
Dead Man / Lockdown
        ↓
Heartbeat กลับมา
        ↓
ยัง LOCKDOWN
        ↓
ต้องได้รับ RESTORE_UPLINK
        ↓
NORMAL
```

สถานะ:

- [x] Heartbeat กลับมาไม่ Auto-Unlock
- [x] ต้องใช้ `RESTORE_UPLINK`
- [x] ทดสอบจริงบน ESP32 + Relay แล้ว

---

# 6. Secure Boot Grace Period

## 6.1 ปัญหาเดิม

Firmware เดิมมี:

```cpp
if (lastHeartbeatMs == 0) return;
```

ทำให้หลัง ESP32 Boot:

```text
ยังไม่เคยได้ Heartbeat
        ↓
return ไปเรื่อย ๆ
        ↓
Relay อยู่ NORMAL ได้โดยไม่มีกำหนด
```

ถือเป็น Boot-State Security Gap

---

## 6.2 การแก้ไข

เพิ่ม:

```text
BOOT_GRACE_MS = 90000
```

พฤติกรรมใหม่:

```text
ESP32 Boot
    ↓
Grace Period 90s
    ↓
Heartbeat มาทัน?
 ┌───────────────┐
 YES             NO
 ↓                ↓
NORMAL      >90s → LOCKDOWN
```

หลังเคยได้รับ Heartbeat แล้ว Dead Man 60 วินาทียังคงทำงานเหมือนเดิม

---

## 6.3 Hardware Validation

### Test A — Heartbeat มาภายใน Grace Period

```text
Boot
→ Wi-Fi
→ NTP
→ MQTT
→ Heartbeat มาภายใน 90s
→ NORMAL
```

ผล:

```text
PASS
```

### Test B — ไม่มี Heartbeat

```text
Boot
→ ไม่มี SOC Heartbeat
→ รอ > 90s
→ SECURE BOOT LOCKDOWN
```

ผล:

```text
Software Lockdown  PASS
LED RED            PASS
Relay Actuation    PASS
```

Serial message:

```text
SECURE BOOT - ไม่พบ Heartbeat ภายใน 90 วิ!
```

---

# 7. Python SOC Command Center

โครงสร้างหลักอยู่ใน:

```text
server_admin.py
aegis_soc/
```

ฟีเจอร์ที่มี:

- [x] ARM / DISARM
- [x] Admin PIN
- [x] CUT_UPLINK
- [x] RESTORE_UPLINK
- [x] MQTT Connection State
- [x] ESP32 Liveness
- [x] RSSI / Heap Telemetry
- [x] Dead Man Countdown
- [x] ACK Tracking
- [x] Incident Lifecycle
- [x] Structured Audit Log
- [x] Export CSV
- [x] UFW response
- [x] Recovery Wizard
- [x] Telegram Alert
- [x] Telegram Remote Control
- [x] Attacker IP Integration
- [x] Software Response Latency instrumentation

---

# 8. Telegram Control / Alert

รองรับคำสั่ง:

```text
/status
/cut <PIN>
/restore <PIN>
```

Security Layers:

```text
1. chat_id validation
2. PIN authentication
3. rate limiting
```

สถานะ:

- [x] Remote `/status`
- [x] Remote `/cut`
- [x] Remote `/restore`
- [x] Telegram LOCKDOWN alert
- [x] Telegram RESTORED alert
- [x] Attacker IP attachment
- [x] Ops event alert

---

# 9. Attack Detection (`detector.py`)

`detector.py` เป็น Attack Detector หลักใน Lab ปัจจุบัน

## 9.1 SSH Brute-Force

Threshold:

```text
5 failed logins
ภายใน 30 วินาที
```

Flow:

```text
Failed SSH Login Logs
        ↓
Detector
        ↓
Threshold reached
        ↓
report_attacker(ip)
```

สถานะ:

- [x] Automated Test
- [x] Kali/Lab Validation
- [x] Automatic Lockdown Flow

---

## 9.2 Port Scan

Threshold:

```text
10 unique ports
ภายใน 10 วินาที
```

Input:

```text
iptables log
AEGIS_NEWCONN
```

สถานะ:

- [x] Automated Test
- [x] Kali/Nmap validation
- [x] Detector → SOC integration

---

## 9.3 SYN Flood / High-Rate TCP Event

เพิ่มใน milestone:

```text
v1.2-syn-flood
```

Lab Threshold:

```text
SYN_FLOOD_THRESHOLD = 20
SYN_FLOOD_WINDOW    = 2 seconds
```

Flow:

```text
AEGIS_NEWCONN
        ↓
SRC IP
        ↓
Sliding Window
        ↓
20 events / 2s
        ↓
report_attacker()
```

Automated tests:

- [x] ต่ำกว่า threshold → ไม่ Alert
- [x] ถึง threshold → Alert

สถานะ:

```text
PASS
```

---

# 10. Automatic Threat Response

MQTT Topic:

```text
aegis/attacker_ip
```

Flow:

```text
Detector
   ↓
publish attacker_ip
   ↓
MQTT Broker
   ↓
SOC on_attacker_detected()
   ↓
ตรวจ ARMED
   ↓
CUT_UPLINK
   ↓
ESP32
   ↓
Relay Lockdown
```

สถานะ:

- [x] Detector → MQTT
- [x] MQTT → SOC
- [x] SOC Auto-CUT
- [x] ESP32 ACK
- [x] Relay Physical Actuation

---

# 11. MQTT Contract

Topics ปัจจุบัน:

```text
aegis/lockdown/cmd
SOC → ESP32

aegis/lockdown/ack
ESP32 → SOC

aegis/heartbeat
SOC → ESP32

aegis/status
ESP32 → SOC

aegis/attacker_ip
Detector → SOC
```

Standalone/Lab:

- [x] Mosquitto Broker
- [x] MQTT username/password authentication
- [x] ESP32 subscribe
- [x] SOC publish/subscribe
- [x] Detector publish

Production MQTT TLS:

```text
PENDING — Integration/Hardening Phase
```

---

# 12. Software Response Latency

Milestone:

```text
v1.3-ms-latency
```

วัดช่วง:

```text
T0 = Detector publish attacker_ip
        ↓
MQTT
        ↓
SOC receives event
        ↓
T2 = ก่อน SOC ออก CUT_UPLINK
```

นิยาม:

```text
Software Response Latency = T2 - T0
```

ผล runtime จริง 5 รอบ:

| Run | Latency |
|---:|---:|
| 1 | 1 ms |
| 2 | 1 ms |
| 3 | 1 ms |
| 4 | 2 ms |
| 5 | 2 ms |

สถิติ:

```text
Samples = 5

Minimum = 1 ms
Maximum = 2 ms
Mean    = 1.4 ms
Median  = 1 ms
Range   = 1 ms
```

สถานะ:

```text
PASS
```

> หมายเหตุ:
> ค่านี้เป็น **Software Response Latency**
> ไม่ใช่ Physical Relay Switching Latency
>
> จึงไม่ควรเขียนว่า Relay ตัดวงจรภายใน 1.4 ms

---

# 13. Tamper-Evident Audit Log

ระบบใช้ SHA-256 Hash Chain

Hash ของแต่ละรายการคำนวณจาก:

```text
timestamp
|
level
|
event_type
|
details
|
previous_hash
```

แนวคิด:

```text
GENESIS
 ↓
Row 1 Hash
 ↓
Row 2 Hash
 ↓
Row 3 Hash
 ↓
...
```

---

# 14. Historical Audit Integrity Anomaly

ระหว่าง Standalone Closure Audit พบว่า:

```text
verify_chain()
→ FAIL ที่ id=162
```

ตรวจสอบเพิ่มเติมพบ Duplicate Hash:

```text
161 / 162
→ DEVICE_STATUS
→ timestamp เดียวกัน
→ details เดียวกัน
→ hash เดียวกัน

163 / 164
→ DEVICE_STATUS
→ timestamp เดียวกัน
→ details เดียวกัน
→ hash เดียวกัน
```

จำนวน Duplicate Hash Groups:

```text
2
```

---

# 15. Audit Race Condition Root Cause

Root Cause ที่ตรวจพบ:

```text
Concurrent Write Race Condition
```

Implementation เดิม:

```text
Thread A                    Thread B
   ↓                           ↓
อ่าน last hash              อ่าน last hash
   ↓                           ↓
ได้ previous hash เดียวกัน
   ↓                           ↓
คำนวณ hash เดียวกัน
   ↓                           ↓
INSERT                      INSERT
```

ทำให้:

```text
row 161 = hash B
row 162 = hash B
```

แต่ chain ที่ถูกต้องควรเป็น:

```text
160 → A
161 → B
162 → C
```

---

# 16. Audit Hash-Chain Fix

Milestone:

```text
v1.5-audit-race-fix
```

แก้ writer ด้วย:

```text
_AUDIT_WRITE_LOCK
+
SQLite BEGIN IMMEDIATE
```

Flow ใหม่:

```text
Acquire Python Lock
        ↓
Open SQLite Connection
        ↓
BEGIN IMMEDIATE
        ↓
Read latest hash
        ↓
Compute next hash
        ↓
INSERT
        ↓
COMMIT
        ↓
Close
        ↓
Release Lock
```

สถานะ:

- [x] ป้องกัน concurrent thread ใน process เดียว
- [x] SQLite writer transaction เริ่มก่อนอ่าน previous hash
- [x] ใช้ connection เดียวในการ read-hash → insert
- [x] Rollback ถ้า transaction error
- [x] File logging เดิมยังอยู่
- [x] Telegram/Ops alerts เดิมยังอยู่

---

# 17. Audit Concurrency Regression Test

เพิ่ม automated test:

```text
test_concurrent_audit_logging_preserves_hash_chain
```

Test จำลอง:

```text
8 Threads
   ↓
Barrier
   ↓
เริ่ม log พร้อมกัน
   ↓
Atomic Writer
   ↓
ตรวจจำนวน Rows
   ↓
verify_chain()
```

ผล:

```text
PASS
```

Automated test suite เพิ่มจาก:

```text
13 tests
```

เป็น:

```text
14 tests
```

สถานะล่าสุด:

```text
14/14 PASS
```

---

# 18. Legacy Audit Evidence Preservation

ฐาน Audit เดิมมี:

```text
audit_logs = 940
```

Known legacy anomaly:

```text
id = 162
```

Historical DB **ไม่ได้ถูก rewrite/re-hash**

เก็บ Evidence นอก Git Repository ที่:

```text
~/AEGIS-evidence/
```

SHA-256 ของ Legacy Ledger:

```text
d3d6a0823f3015363cc63b78d85dde000d23dc629face14e13925e1608073298
```

สำเนาที่ตรวจแล้วมี SHA-256 ตรงกันแบบ byte-for-byte

แนวทาง:

```text
Legacy Ledger
→ Preserve
→ ไม่แก้ย้อนหลัง

New Ledger
→ เริ่มใหม่หลัง v1.5 fix
```

---

# 19. Active Audit Ledger Rotation

หลังแก้ race condition:

- [x] SOC process ถูกปิดก่อน rotation
- [x] ไม่มี Open Incident
- [x] SQLite Journal Mode = `delete`
- [x] ไม่มี WAL/SHM sidecar
- [x] Legacy DB ถูกย้ายออกจาก active runtime
- [x] Legacy Evidence SHA-256 ถูกยืนยัน
- [x] New `aegis_audit.db` ถูก Initialize
- [x] New ledger เริ่มจาก GENESIS
- [x] เพิ่ม Start Marker

First event:

```text
SYSTEM
AUDIT LEDGER START - post-v1.5 hash-chain race fix
```

หลังสร้าง:

```text
verify_chain() = PASS
```

---

# 20. New Ledger Runtime Validation

หลังเปิด SOC + ESP32 Runtime จริง:

```text
audit_logs = 9
```

Event Counts:

```text
ACK_RECEIVED  = 1
COMMAND_SENT  = 1
DEVICE_STATUS = 3
SYSTEM        = 4
```

ผล:

```text
verify_chain() = PASS
Duplicate Hash Groups = 0
```

จุดสำคัญคือ `DEVICE_STATUS` ซึ่งเป็น event ชนิดเดียวกับที่เคยเกิด Race Condition ใน Legacy DB ถูกเขียนใหม่ใน runtime จริงแล้วแต่ไม่เกิด Duplicate Hash

สถานะ:

```text
Historical anomaly detected       PASS
Root cause identified             PASS
Evidence preserved                PASS
Implementation fixed              PASS
Concurrency regression            PASS
Runtime DEVICE_STATUS validation  PASS
New active ledger integrity       PASS
```

---

# 21. Incident Model / Recovery

Incident Lifecycle:

```text
OPEN
 ↓
CONTAINED
 ↓
CLOSED
```

Recovery Wizard:

```text
1. Out-of-band Access
2. Block Attacker IP
3. Restore Physical Uplink
4. Reopen Services
5. Lessons Learned / Close Incident
```

สถานะ:

- [x] Incident model
- [x] Recovery Wizard
- [x] UFW Block
- [x] RESTORE workflow
- [x] Closed-loop recovery

---

# 22. UFW Threat Response

IDEA 3 ใช้ UFW สำหรับ:

```text
Threat Response / Attacker IP Blocking
```

ไม่ใช่หน้าที่เดียวกับ Access Policy ของ IDEA 1

Standalone/Lab:

- [x] UFW command path
- [x] IP validation
- [x] pkexec path
- [x] Recovery Wizard integration

Production IDEA 1 UFW Integration:

```text
PENDING — Integration Phase
```

---

# 23. Secret Management / Repository Safety

Secret หลัก:

```text
.env
src/secrets.h
```

สถานะ:

- [x] `.env` มีอยู่เฉพาะ local
- [x] `src/secrets.h` มีอยู่เฉพาะ local
- [x] `.gitignore` ป้องกันทั้งสองไฟล์
- [x] ตรวจแล้วว่า `.env` ไม่ Track
- [x] ตรวจแล้วว่า `src/secrets.h` ไม่ Track
- [x] HMAC Secret ฝั่ง SOC/ESP32 เคยตรวจว่า Match
- [x] ไม่เก็บ Production Secret ใน README/PROGRESS

Git workflow:

```text
one task
→ one branch
→ tests
→ lint
→ explicit git add
→ commit
→ push
→ Pull Request
→ merge main
→ tag milestone
```

---

# 24. Automated Test / Code Quality

สถานะล่าสุด:

```text
pytest = 14/14 PASS
ruff check . = PASS
PlatformIO Build = PASS
```

Test ครอบคลุมอย่างน้อย:

```text
HMAC valid
HMAC tamper
Nonce uniqueness
PIN
Incident lifecycle
Config validation
Invalid IP
Concurrent Audit Hash Chain
SSH brute-force
Below-threshold SSH
Normal detector input
Port Scan
SYN Flood below threshold
SYN Flood trigger threshold
```

---

# 25. Firmware Resource Usage

PlatformIO Build ล่าสุด:

```text
RAM:
14.2%
46572 / 327680 bytes

Flash:
60.2%
788913 / 1310720 bytes
```

สถานะ:

```text
Firmware Build = SUCCESS
```

---

# 26. Git / Version History

Current canonical:

```text
main = a6d5630
tag  = v1.5-audit-race-fix
```

Milestones:

```text
v1.0-standalone
v1.1-pentested
v1.2-syn-flood
v1.3-ms-latency
v1.4-secure-boot
v1.5-audit-race-fix
```

Current Git State:

```text
main
origin/main synced
working tree clean
```

---

# 27. Historical / Lessons Learned

งานเก่าที่เก็บเป็นประวัติการพัฒนา:

- แก้ Serial Monitor ทำให้ ESP32 reset ผ่าน DTR/RTS configuration
- เพิ่ม Timestamp Window + NTP
- เพิ่ม HMAC Heartbeat
- เปลี่ยน MQTT reconnect จาก blocking เป็น non-blocking
- เพิ่มไฟแดงกระพริบแบบ non-blocking
- แก้ `sim_auto_detector.py` ที่เคยปลอม status ให้ใช้ secure command จริง
- แก้ `.env` load-order
- แยก detector MQTT connection ออกจาก import-time execution
- เพิ่ม Ruff/Lint baseline
- เพิ่ม SYN Flood detection
- เพิ่ม millisecond latency instrumentation
- เพิ่ม Secure Boot Grace Period
- ตรวจพบและแก้ Audit Hash-Chain concurrent-write race
- ทำ Ledger Rotation หลังแก้ Audit Writer

---

# 28. สิ่งที่ยังเหลือใน Standalone / Lab

## 28.1 Power Measurement

- [ ] วัดพลังงานจริงของ ESP32 + Relay ด้วย USB Power Meter

ต้องเก็บอย่างน้อย:

```text
NORMAL:
Voltage
Current
Power

LOCKDOWN:
Voltage
Current
Power
```

จากนั้นคำนวณ:

```text
Wh/day = Power (W) × 24h
```

สถานะ:

```text
PENDING — awaiting USB Power Meter
```

> ห้ามใช้ค่าประมาณเป็นผลการทดลองจริง

---

# 29. Documentation Closure

ยังต้องอัปเดตเอกสารหลักให้ตรงกับ `v1.5`

- [ ] อัปเดตบทที่ 4–5
- [ ] เพิ่ม SYN Flood
- [ ] เพิ่ม Software Response Latency
- [ ] เพิ่ม Secure Boot Grace Period
- [ ] เพิ่ม Audit Race Condition Root Cause/Fix
- [ ] เพิ่ม Legacy Ledger Evidence Handling
- [ ] เพิ่ม New Ledger Runtime Validation
- [ ] ระบุ Power Measurement เป็น Pending
- [ ] แยก Standalone Validation กับ Production Integration ชัดเจน

---

# 30. Production Integration — ทำภายหลังเมื่อรวม IDEA 1–2

## 30.1 Network / VLAN

- [ ] ตรวจ Production MQTT Broker / Service Address
- [ ] ย้าย SOC จาก Hotspot Lab เข้า AEGIS Network
- [ ] ย้าย ESP32 เข้า Network/VLAN ที่กำหนด
- [ ] ยืนยัน Routing / Firewall contract ระหว่าง Zone

Production architecture ใช้:

```text
VLAN 10 = Server Zone
VLAN 20 = Detector Zone
VLAN 30 = Management Zone
```

---

## 30.2 IDEA 2 Integration

เป้าหมาย:

```text
IDEA 2 Detection Engine
        ↓
attacker IP / event
        ↓
aegis/attacker_ip
        ↓
IDEA 3
```

- [ ] ยืนยัน Detection Engine จริง
- [ ] ยืนยัน attacker-event contract
- [ ] ทดสอบ IDEA 2 → IDEA 3 E2E

---

## 30.3 IDEA 1 Integration

IDEA 1 เป็น NAS/Data Layer ที่ IDEA 3 ต้องปกป้อง

- [ ] เชื่อม UFW threat response กับ NAS จริง
- [ ] ตรวจ permission / pkexec
- [ ] ยืนยัน Management path ยังเข้าได้หลัง Lockdown

---

## 30.4 Physical WAN Integration

เป้าหมาย:

```text
Internet / WAN
      │
    Relay
      │
Protected NAS Path
```

หลักสำคัญ:

```text
LOCKDOWN
→ ตัด WAN/Uplink

แต่ต้องไม่ตัด:
LAN
Management VLAN
Recovery Path
```

- [ ] ต่อ Relay เข้าสาย WAN/Uplink จริง
- [ ] ยืนยัน NORMAL → Internet reachable
- [ ] ยืนยัน LOCKDOWN → WAN unavailable
- [ ] ยืนยัน Management/LAN ยัง reachable
- [ ] ยืนยัน RESTORE คืนระบบได้

---

# 31. Production Hardening ที่ยังเหลือ

- [ ] MQTT TLS
- [ ] systemd service
- [ ] watchdog / auto-restart
- [ ] persistent detection logging rules
- [ ] Production secret/config validation
- [ ] จูน `DEADMAN_TIMEOUT_MS` จากเวลา boot/recovery จริงของ NAS
- [ ] ตรวจ Secure Boot Grace Period กับ Production boot behavior
- [ ] ตรวจ resource monitoring / reliability

---

# 32. Production Cyber-Physical End-to-End Test

Final Integration Flow ที่ต้องพิสูจน์:

```text
Attack / Detection Event
        ↓
IDEA 2 / IDS
        ↓
attacker_ip
        ↓
Production MQTT
        ↓
IDEA 3 SOC
        ↓
HMAC + Nonce + Timestamp
        ↓
CUT_UPLINK
        ↓
ESP32
        ↓
Physical WAN Isolation
        ↓
ACK
        ↓
UFW Threat Block
        ↓
Audit / Incident
        ↓
Telegram
        ↓
Management Recovery
        ↓
RESTORE
        ↓
NORMAL
```

สถานะ:

```text
PENDING — Production Integration Phase
```

---

# 33. Current Standalone Closure Status

สถานะ ณ `v1.5-audit-race-fix`:

```text
Core Protocol Security         PASS
ESP32 Firmware                 PASS
Physical Relay Control         PASS
Dead Man's Switch              PASS
Explicit Recovery              PASS
Secure Boot Grace Period       PASS
SSH Brute-force Detector       PASS
Port Scan Detector             PASS
SYN Flood Detector             PASS
Automatic Lockdown             PASS
MQTT Standalone                PASS
Telegram Control/Alert         PASS
Incident / Recovery            PASS
Software Response Latency      PASS
Tamper-Evident Audit Fix       PASS
Audit Concurrency Regression   PASS
New Ledger Runtime Integrity   PASS
Automated Tests                14/14 PASS
Ruff                           PASS
Firmware Build                 PASS

Power Measurement              PENDING
Production Integration         PENDING
```

---

# 34. Current Standalone Result

สามารถสรุปได้ว่า:

> AEGIS IDEA 3 ในระดับ Standalone/Lab มีองค์ประกอบหลักของระบบ Cyber-Physical Active Defense ทำงานครบแล้ว ได้แก่ การตรวจจับภัย การส่ง attacker event ผ่าน MQTT การออกคำสั่งที่ป้องกันด้วย HMAC/Nonce/Timestamp การตัดวงจรกายภาพผ่าน ESP32/Relay ระบบ Dead Man's Switch ระบบ Secure Boot Grace Period การ Recovery แบบ Explicit การบันทึก Audit แบบ Tamper-Evident และการแจ้งเตือน/กู้คืนเหตุการณ์

การพัฒนาล่าสุดตรวจพบปัญหา concurrent-write race condition ใน Audit Hash Chain จากการใช้งานจริง โดยพบ duplicate hash ใน Historical Ledger จาก `DEVICE_STATUS` ที่เกิดพร้อมกัน ทีมได้เก็บฐานเดิมไว้เป็น forensic evidence โดยไม่แก้ไขย้อนหลัง จากนั้นแก้ Audit Writer ให้ใช้ Lock และ SQLite `BEGIN IMMEDIATE` เพิ่ม concurrency regression test และเปิด Active Ledger ใหม่

ผล runtime หลังแก้พบว่า:

```text
verify_chain() = PASS
DEVICE_STATUS runtime = PASS
duplicate hash groups = 0
```

ดังนั้น Audit subsystem รุ่นใหม่ได้รับการยืนยันทั้งใน automated test และ runtime จริงแล้ว

---

# 35. งานถัดไป

ลำดับงานจากจุดปัจจุบัน:

```text
1. รอ USB Power Meter
        ↓
2. วัด NORMAL / LOCKDOWN Power
        ↓
3. อัปเดตบทที่ 4–5 / เอกสาร Final Standalone
        ↓
4. Standalone IDEA 3 Closure
        ↓
5. Production Integration Readiness
        ↓
6. MQTT / VLAN Integration
        ↓
7. IDEA 2 → IDEA 3 Integration
        ↓
8. IDEA 1 / UFW Integration
        ↓
9. Physical WAN Relay Integration
        ↓
10. MQTT TLS / systemd / watchdog
        ↓
11. Production Cyber-Physical E2E
        ↓
12. Final Report / Evidence
```

---

# สรุปสั้น ๆ

AEGIS IDEA 3 ปัจจุบันอยู่ที่ milestone:

```text
v1.5-audit-race-fix
main = a6d5630
```

ระบบ Standalone ผ่านการทดสอบหลักแล้ว ได้แก่:

```text
Secure Command Protocol
Dead Man's Switch
Explicit Recovery
Secure Boot Grace Period
SSH Brute-force Detection
Port Scan Detection
SYN Flood Detection
Automatic Physical Lockdown
Software Response Latency
Telegram
Incident Recovery
Tamper-Evident Audit Log
Concurrent Audit Write Protection
```

ผล Validation ล่าสุด:

```text
pytest            = 14/14 PASS
ruff              = PASS
ESP32 build       = PASS
Software latency  = mean 1.4 ms
Secure Boot Grace = 90s PASS
Dead Man Timeout  = 60s PASS
New Audit Ledger  = PASS
Duplicate Hash    = 0
```

สิ่งที่ยังเหลือใน Standalone คือ:

```text
Power Measurement
→ รอ USB Power Meter
```

ส่วน VLAN, IDEA 1, IDEA 2, MQTT TLS, systemd/watchdog, UFW Production และ Relay WAN จริง จะดำเนินการใน Production Integration Phase ภายหลัง
