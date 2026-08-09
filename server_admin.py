#!/usr/bin/env python3
"""
AEGIS IDEA 3 — SOC Command Center (entry point)
โครงสร้างแยกเป็นโมดูลในแพ็กเกจ aegis_soc/ แต่ยังรันด้วยคำสั่งเดิม:

    python3 server_admin.py

ตั้งค่าความลับผ่าน environment variable ก่อนรัน (ดู README):
    export AEGIS_TG_TOKEN="..."   export AEGIS_TG_CHAT="..."
"""
from aegis_soc.gui import main

if __name__ == "__main__":
    main()
