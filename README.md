# AEGIS IDEA 3 — Cyber-Physical Lockdown

> **Current canonical version:** `v1.5-audit-race-fix`
> **Current main:** `a6d5630`
> **Status:** Standalone/Lab core validated; Production Integration pending
> **Automated validation:** `pytest` 14/14 PASS · `ruff check .` PASS · PlatformIO build PASS

AEGIS IDEA 3 เป็นระบบ **Cyber-Physical Active Defense** สำหรับตรวจจับภัยคุกคามทางไซเบอร์และตอบโต้ด้วยการตัด Uplink ทางกายภาพผ่าน ESP32 + Relay โดยออกแบบให้ทำงานร่วมกับ AEGIS IDEA 1 และ IDEA 2 ใน Production Integration Phase

```text
Attack / Suspicious Activity
        ↓
Attack Detector
        ↓
MQTT attacker_ip
        ↓
SOC Command Center
        ↓
HMAC + Nonce + Timestamp
        ↓
CUT_UPLINK
        ↓
ESP32 + Relay
        ↓
Physical Lockdown
        ↓
ACK / Audit / Alert
        ↓
Explicit Recovery
```

---

## Current Status

ฟังก์ชันหลักที่ยืนยันแล้วใน Standalone/Lab:

- HMAC-SHA256 command authentication
- Nonce Anti-Replay
- Timestamp Window 30 วินาที
- MQTT username/password authentication
- ESP32 + Relay physical CUT / RESTORE
- Dead Man's Switch 60 วินาที
- Secure Boot Grace Period 90 วินาที
- Explicit Recovery — Heartbeat กลับมาแล้วไม่ Auto-Unlock
- SSH Brute-force Detection
- Port Scan Detection
- SYN Flood / High-rate TCP Detection
- Automatic Detector → SOC → ESP32 Lockdown
- Telegram Control / Alert
- Incident Recovery Workflow
- Software Response Latency instrumentation
- Tamper-Evident Audit Hash Chain
- Concurrent Audit Writer race-condition protection
- Runtime validation ของ Active Audit Ledger

สิ่งที่ยังเหลือใน Standalone:

- **Power Measurement ด้วย USB Power Meter**

สิ่งที่ยังไม่ถือว่าเสร็จ:

- Production VLAN Integration
- IDEA 1 / IDEA 2 Integration
- Production MQTT TLS
- systemd / watchdog
- Physical WAN Relay Integration บน topology จริง

รายละเอียดทั้งหมดดูที่ [`PROGRESS.md`](PROGRESS.md)

---

## Architecture

องค์ประกอบหลัก:

```text
┌───────────────────────┐
│ Attack Detector       │
│ detector.py           │
└──────────┬────────────┘
           │ aegis/attacker_ip
           ▼
┌───────────────────────┐
│ MQTT Broker           │
│ Mosquitto             │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ SOC Command Center    │
│ Python / Tkinter      │
└──────────┬────────────┘
           │ Secure MQTT Command
           ▼
┌───────────────────────┐
│ ESP32                 │
│ HMAC verification     │
│ Dead Man / Boot Grace │
└──────────┬────────────┘
           │ GPIO 27
           ▼
┌───────────────────────┐
│ Relay                 │
│ Physical Lockdown     │
└───────────────────────┘
```

---

## Repository Structure

```text
AEGIS_IDEA3/
├── server_admin.py
├── detector.py
├── sim_auto_detector.py
├── PROGRESS.md
├── README.md
├── pytest.ini
├── ruff.toml
├── platformio.ini
│
├── aegis_soc/
│   ├── __init__.py
│   ├── config.py
│   ├── security.py
│   ├── mqtt_client.py
│   ├── database.py
│   ├── comms.py
│   ├── telegram_control.py
│   ├── gui.py
│   ├── wizard.py
│   └── theme.py
│
├── src/
│   ├── main.cpp
│   ├── secrets.h.example
│   └── secrets.h          # local secret — DO NOT COMMIT
│
└── tests/
    ├── test_core.py
    └── test_detector.py
```

---

## Core MQTT Contract

| Topic | Direction | Purpose |
|---|---|---|
| `aegis/lockdown/cmd` | SOC → ESP32 | Secure CUT / RESTORE command |
| `aegis/lockdown/ack` | ESP32 → SOC | Command acknowledgement |
| `aegis/heartbeat` | SOC → ESP32 | Liveness heartbeat |
| `aegis/status` | ESP32 → SOC | Device / lockdown status |
| `aegis/attacker_ip` | Detector → SOC | Detected attacker IP |

Production Integration ควรรักษา MQTT contract ชุดนี้ไว้เพื่อให้ IDEA 2 สามารถส่ง attacker event เข้า IDEA 3 ได้โดยไม่ต้องเปลี่ยน SOC logic หลัก

---

## Security Model

### Secure Command

คำสั่งที่ส่งไป ESP32 ประกอบด้วย:

```text
action
nonce
timestamp
HMAC-SHA256 signature
```

ESP32 ตรวจตามลำดับ:

```text
JSON
 ↓
Timestamp
 ↓
Nonce
 ↓
HMAC
 ↓
Execute
 ↓
ACK
```

ค่าปัจจุบัน:

```text
MAX_COMMAND_AGE_SEC = 30
NONCE_HISTORY_SIZE  = 20
```

---

## Dead Man's Switch

SOC ส่ง Heartbeat ให้ ESP32 อย่างต่อเนื่อง

```text
Heartbeat received
      ↓
lastHeartbeatMs updated
      ↓
Heartbeat missing > 60s
      ↓
LOCKDOWN
```

ค่า:

```text
DEADMAN_TIMEOUT_MS = 60000
```

MQTT reconnect ฝั่ง ESP32 เป็น non-blocking เพื่อให้ `checkDeadman()` ยังทำงานได้แม้ Broker หลุด

---

## Secure Boot Grace Period

ตั้งแต่ `v1.4-secure-boot`:

```text
ESP32 Boot
    ↓
รอ Heartbeat สูงสุด 90s
    ↓
Heartbeat มา?
 ┌─────────────┐
 YES           NO
 ↓              ↓
NORMAL      LOCKDOWN
```

ค่า:

```text
BOOT_GRACE_MS = 90000
```

Hardware validation:

```text
Heartbeat within Grace Period → PASS
No Heartbeat > 90s            → LOCKDOWN PASS
LED RED                        → PASS
Relay Actuation                → PASS
```

---

## Explicit Recovery

ระบบไม่ปลด Lockdown อัตโนมัติเพียงเพราะ Heartbeat กลับมา

```text
LOCKDOWN
   ↓
Heartbeat returns
   ↓
still LOCKDOWN
   ↓
RESTORE_UPLINK required
   ↓
NORMAL
```

ช่วยป้องกันการกลับ Online โดยไม่มีการยืนยันจากผู้ดูแลหลังเกิดเหตุ

---

## Attack Detector

ไฟล์หลัก:

```text
detector.py
```

### SSH Brute-force

```text
Threshold = 5 failed logins
Window    = 30 seconds
```

### Port Scan

```text
Threshold = 10 unique ports
Window    = 10 seconds
```

Input ใช้ log prefix:

```text
AEGIS_NEWCONN
```

### SYN Flood / High-rate TCP

```text
Threshold = 20 events
Window    = 2 seconds
```

มี automated tests สำหรับทั้ง below-threshold และ trigger-threshold

---

## Automatic Lockdown Flow

```text
Detector detects attacker
        ↓
report_attacker(ip)
        ↓
publish aegis/attacker_ip
        ↓
SOC receives attacker IP
        ↓
ตรวจว่า ARMED
        ↓
send CUT_UPLINK
        ↓
ESP32 validates command
        ↓
Relay Lockdown
        ↓
ACK
```

---

## SOC Command Center

รันผ่าน:

```bash
python3 server_admin.py
```

ฟีเจอร์หลัก:

- ARM / DISARM
- CUT / RESTORE
- Admin PIN
- MQTT Connection State
- ESP32 Liveness
- RSSI / Heap
- Dead Man Countdown
- ACK Tracking
- Incident Lifecycle
- Audit Log
- CSV Export
- UFW Response
- Recovery Wizard
- Telegram
- Attacker IP integration
- Software latency measurement

---

## Telegram

รองรับ:

```text
/status
/cut <PIN>
/restore <PIN>
```

Security:

```text
chat_id
  +
PIN
  +
rate limiting
```

---

## Software Response Latency

ตั้งแต่ `v1.3-ms-latency` ระบบวัดช่วง:

```text
Detector publish attacker_ip
        ↓
MQTT
        ↓
SOC receives event
        ↓
SOC issues CUT_UPLINK
```

ผล runtime 5 รอบ:

```text
1 ms
1 ms
1 ms
2 ms
2 ms
```

สรุป:

```text
Minimum = 1 ms
Maximum = 2 ms
Mean    = 1.4 ms
Median  = 1 ms
```

> **สำคัญ:** ตัวเลขนี้คือ **Software Response Latency** ไม่ใช่ Physical Relay Switching Latency

---

## Tamper-Evident Audit Log

Audit Log ใช้ SHA-256 Hash Chain:

```text
GENESIS
   ↓
Row 1 Hash
   ↓
Row 2 Hash
   ↓
Row 3 Hash
```

Hash คำนวณจาก:

```text
timestamp
level
event_type
details
previous_hash
```

ตรวจด้วย:

```bash
python3 -c "from aegis_soc import database as db; print(db.verify_chain())"
```

---

## Audit Concurrent-Write Race Fix

ระหว่าง Standalone Closure พบ Historical Ledger มี duplicate hash ที่ `DEVICE_STATUS`

Root Cause:

```text
Concurrent writers
→ อ่าน previous hash เดียวกัน
→ คำนวณ next hash จาก parent เดียวกัน
→ เกิด duplicate hash / broken chain
```

ตั้งแต่ `v1.5-audit-race-fix` แก้ด้วย:

```text
threading.Lock
+
SQLite BEGIN IMMEDIATE
```

ทำให้ขั้นตอน:

```text
read previous hash
→ compute
→ insert
→ commit
```

อยู่ใน serialized transaction

เพิ่ม regression test:

```text
test_concurrent_audit_logging_preserves_hash_chain
```

ผล:

```text
14/14 tests PASS
```

Historical DB ถูกเก็บเป็น Evidence โดย **ไม่ rewrite/re-hash ย้อนหลัง**

Active Ledger ใหม่หลัง fix ผ่าน runtime validation:

```text
verify_chain()          = PASS
duplicate hash groups   = 0
DEVICE_STATUS runtime   = PASS
```

---

## Incident Recovery

Lifecycle:

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

---

## Hardware

ESP32 GPIO:

```text
Relay       GPIO 27
Green LED   GPIO 32
Red LED     GPIO 33
```

Relay logic:

```text
RELAY_RELEASE = HIGH
RELAY_TRIGGER = LOW
```

Firmware build ล่าสุด:

```text
RAM   14.2%  (46572 / 327680 bytes)
Flash 60.2%  (788913 / 1310720 bytes)
```

---

## Requirements

Python environment ต้องมีอย่างน้อย:

```text
paho-mqtt
pytest
ruff
```

PlatformIO ใช้สำหรับ ESP32 firmware

Dependencies หลักของ firmware:

```text
PubSubClient
ArduinoJson
WiFi
```

---

## Configuration

### SOC `.env`

สร้าง `.env` ใน project root

ตัวอย่าง:

```dotenv
AEGIS_BROKER_IP=127.0.0.1
AEGIS_BROKER_PORT=1883

AEGIS_MQTT_USER=aegis
AEGIS_MQTT_PASS=<mqtt-password>

AEGIS_HMAC_SECRET=<shared-hmac-secret>
AEGIS_ADMIN_PIN=<admin-pin>

AEGIS_TG_TOKEN=<telegram-token>
AEGIS_TG_CHAT=<telegram-chat-id>
```

> `.env` เป็น Secret และต้องไม่ Commit

### ESP32 Secrets

ใช้:

```text
src/secrets.h
```

โดยอ้างอิง template:

```text
src/secrets.h.example
```

Secret หลัก:

```text
SECRET_WIFI_SSID
SECRET_WIFI_PASSWORD
SECRET_HMAC_KEY
SECRET_MQTT_USER
SECRET_MQTT_PASS
```

> `src/secrets.h` ต้องไม่ Commit

---

## Quick Start — Standalone/Lab

### 1. เข้า Project

```bash
cd "/path/to/AEGIS_IDEA3"
```

### 2. เปิด Python environment

```bash
source venv/bin/activate
```

### 3. Start Mosquitto

```bash
sudo systemctl start mosquitto
```

### 4. Start SOC

```bash
python3 server_admin.py
```

จากนั้นกด:

```text
ARM
```

ก่อนทดสอบ Automatic Response

### 5. Start Detector

```bash
sudo python3 detector.py
```

### 6. ESP32

Build:

```bash
pio run
```

Upload:

```bash
pio run -t upload
```

Serial Monitor:

```bash
pio device monitor -b 115200
```

---

## Validation

ก่อน Push ทุกครั้ง:

```bash
pytest -v
ruff check .
pio run
git diff --check
git status
```

Expected current baseline:

```text
pytest      14/14 PASS
ruff        PASS
pio run     SUCCESS
```

---

## Git Safety

Secret files:

```text
.env
src/secrets.h
```

ต้องไม่ถูก Track

ตรวจ:

```bash
git status
git ls-files .env src/secrets.h
```

ก่อน commit ใช้ explicit staging:

```bash
git add <specific-files>
```

หลีกเลี่ยงการ stage secret หรือ runtime evidence โดยไม่ตรวจสอบก่อน

---

## Current Git Milestones

```text
v1.0-standalone
v1.1-pentested
v1.2-syn-flood
v1.3-ms-latency
v1.4-secure-boot
v1.5-audit-race-fix
```

Current canonical baseline:

```text
main = a6d5630
tag  = v1.5-audit-race-fix
```

---

## Production Integration Plan

Standalone/Lab กับ Production ต้องแยกสถานะกัน

Production Architecture:

```text
VLAN 10 = Server Zone
VLAN 20 = Detector Zone
VLAN 30 = Management Zone
```

งาน Production ที่ยังเหลือ:

- Production MQTT Broker / address validation
- ESP32 network migration
- IDEA 2 → `aegis/attacker_ip`
- IDEA 1 UFW integration
- Physical WAN Relay
- MQTT TLS
- systemd / watchdog
- Dead Man timeout tuning
- Production Cyber-Physical E2E

---

## IDEA 1 / IDEA 2 Integration Contract

### IDEA 2

IDEA 2 ทำหน้าที่ Detection:

```text
IDEA 2
   ↓
detected attacker
   ↓
publish attacker IP
   ↓
aegis/attacker_ip
   ↓
IDEA 3
```

### IDEA 1

IDEA 3 ปกป้อง NAS/Data Layer ของ IDEA 1

Production response:

```text
IDEA 3
   ↓
Physical WAN isolation
   +
UFW threat response
```

Management/LAN recovery path ต้องยังอยู่หลัง Lockdown

---

## Remaining Standalone Work

งาน Standalone ที่ยังเหลือ:

### Power Measurement

รอ USB Power Meter

ต้องวัด:

```text
NORMAL
- Voltage
- Current
- Power

LOCKDOWN
- Voltage
- Current
- Power
```

คำนวณ:

```text
Wh/day = Power (W) × 24
```

> ห้ามใช้ค่าประมาณเป็นผลการทดลองจริง

---

## Current Result

สถานะ `v1.5-audit-race-fix`:

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

## Next Steps

```text
USB Power Meter arrives
        ↓
Power Measurement
        ↓
Standalone Documentation Closure
        ↓
Production Integration Readiness
        ↓
MQTT / VLAN Integration
        ↓
IDEA 2 Integration
        ↓
IDEA 1 / UFW Integration
        ↓
Physical WAN Relay
        ↓
MQTT TLS / systemd / watchdog
        ↓
Production Cyber-Physical E2E
```

---

## Safety / Scope

ระบบและเครื่องมือทดสอบของโครงการนี้มีไว้สำหรับ **เครื่องและเครือข่าย Lab ที่ได้รับอนุญาตเท่านั้น**

การทดสอบ Kali / Detector / Network Security ต้องดำเนินการเฉพาะในสภาพแวดล้อมที่ทีมเป็นเจ้าของหรือได้รับอนุญาตให้ทดสอบ

---

## Documentation

เอกสารสถานะละเอียด:

```text
PROGRESS.md
```

Source-of-truth สำหรับสถานะปัจจุบันควรยึด:

1. Current `main`
2. Current milestone tag
3. Automated tests
4. Hardware/runtime evidence
5. `PROGRESS.md`

หากเอกสารเก่าขัดกับผลทดสอบล่าสุด ให้ถือเอกสารเก่าเป็น Historical Context และใช้ Current Verified State เป็นหลัก
