# AEGIS IDEA 3 — SOC Command Center (v2, modular)

โปรแกรมเฝ้าระวัง+ตอบโต้ (Security Operations Center) สำหรับ Cyber-Physical Lockdown
ยกระดับเป็นเกรดใช้งานจริง: มีโหมดควบคุม, ติดตาม ACK, สถานะอุปกรณ์สด, log แบ่งระดับ และโมเดล Incident

## วิธีรัน
```bash
# ตั้งค่าความลับผ่าน environment variable (ไม่ตั้งก็รันได้ แต่จะไม่ส่ง Telegram)
export AEGIS_TG_TOKEN="<telegram bot token ใหม่>"
export AEGIS_TG_CHAT="<chat id>"
export AEGIS_HMAC_SECRET="<ต้องตรงกับ ESP32>"   # ไม่ตั้ง = ใช้ค่า default เดโม
export AEGIS_ADMIN_PIN="<PIN>"                    # ไม่ตั้ง = 1234
# ตอนขึ้น topology จริง (VLAN 10):
# export AEGIS_BROKER_IP="192.168.10.13"

python3 server_admin.py
```
> รันด้วยคำสั่งเดิม `python3 server_admin.py` — ข้างในแยกเป็นโมดูลในโฟลเดอร์ `aegis_soc/`

## โครงสร้างโมดูล
| ไฟล์ | หน้าที่ |
|---|---|
| `server_admin.py` | จุดเริ่มโปรแกรม (เรียก `aegis_soc.gui.main`) |
| `aegis_soc/config.py` | ค่าตั้งทั้งหมด + อ่าน env + ตรวจ config + hash PIN |
| `aegis_soc/security.py` | สร้าง payload เซ็น HMAC + nonce + timestamp |
| `aegis_soc/database.py` | audit log (มีระดับความรุนแรง) + โมเดล Incident + log ไฟล์หมุนเวียน |
| `aegis_soc/comms.py` | Telegram (สองภาษา + ops) + UFW containment |
| `aegis_soc/mqtt_client.py` | MQTT + สถานะ broker + device liveness + ส่งต่อ ACK |
| `aegis_soc/theme.py` | สี/ฟอนต์/วิดเจ็ตที่ใช้ร่วมกัน |
| `aegis_soc/wizard.py` | Incident Recovery Wizard 5 ขั้น (ผูกกับ Incident) |
| `aegis_soc/gui.py` | หน้าจอหลัก (ARM/DISARM, controls, log, banner) |

## ฟีเจอร์ที่เพิ่มในรอบนี้ (4 กลุ่ม)
1. **การควบคุม** — ARM/DISARM (โหมดเฝ้าระวัง vs ซ่อมบำรุง), ยืนยันคำสั่งซ้อน (PIN + พิมพ์ CONFIRM) สำหรับ CUT, ล็อกหลังใส่ PIN ผิดหลายครั้ง
2. **ความน่าเชื่อถือ** — ติดตาม ACK ของคำสั่ง (ไม่มี ACK ใน 8s = เตือน), สถานะ ESP32 แยกจาก broker (online/last-seen), ตรวจ config ตอนเริ่ม, ปิดโปรแกรมอย่างเรียบร้อย
3. **การมองเห็น** — log ระดับ INFO/WARN/CRITICAL ลงสี + กรองได้, เขียนไฟล์ `aegis_soc.log` แบบหมุนเวียน
4. **โครงสร้าง** — โมเดล Incident (OPEN→CONTAINED→CLOSED) + banner สรุป, แยกโค้ดเป็นโมดูล

## หมายเหตุการออกแบบ (สำคัญ)
- **Dead Man's Switch countdown** นับจาก heartbeat ที่ GUI **ส่งสำเร็จ** ล่าสุด (ตรงกับตรรกะฝั่ง ESP32 ที่ตัดเน็ตเมื่อไม่ได้รับ heartbeat) — ถ้า broker หลุด ตัวเลขจะลดลงเพื่อเตือนว่า ESP32 กำลังจะตัดเน็ตเอง
- **DISARM** เป็นการควบคุมฝั่ง GUI (ปิดปุ่มตัดเน็ต + ยังส่ง heartbeat กัน ESP32 ตัดเน็ตเองระหว่างซ่อม) หากต้องการให้ DISARM ระงับ Dead Man's Switch ฝั่งบอร์ดด้วย ต้องเพิ่มคำสั่ง ARM/DISARM ในเฟิร์มแวร์ (งานเสริมในอนาคต)
- **การโจมตี/ทดสอบ** ใช้ Kali Linux ยิงจากภายนอก — โปรแกรมนี้ไม่มีฟังก์ชันโจมตีในตัว

## ความปลอดภัย
ก่อน push ขึ้น GitHub: revoke Telegram token เก่า + ออกใหม่, ตั้ง secret ผ่าน env, และใช้ `.gitignore` ที่แนบมา (กัน secret / `aegis_audit.db` / log หลุด)
