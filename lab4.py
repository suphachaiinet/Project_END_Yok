import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab4_bp = Blueprint('lab4', __name__)

# ----------------------------------------------------------------------
# ฟังก์ชันแยกบล็อกของ interface
# ----------------------------------------------------------------------
def parse_interfaces(config_text):
    """
    แยก interface และคำสั่งที่เกี่ยวข้องออกเป็นบล็อก
    """
    interfaces = {}
    current_interface = None
    lines = config_text.splitlines()

    for line in lines:
        line = line.strip()
        if line.startswith("interface"):
            current_interface = line
            interfaces[current_interface] = []
        elif current_interface and line:
            interfaces[current_interface].append(line)
    return interfaces

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบคำสั่งในบล็อกของ interface
# ----------------------------------------------------------------------
def check_interface_block(interface_block, expected_commands):
    """
    ตรวจสอบว่า interface block มีคำสั่งครบถ้วนตาม expected_commands หรือไม่
    """
    missing_commands = [cmd for cmd in expected_commands if cmd not in interface_block]
    return missing_commands

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบคีย์เวิร์ด
# ----------------------------------------------------------------------
def check_keywords(user_config, keywords):
    """
    เปรียบเทียบคำตอบของผู้ใช้กับคีย์เวิร์ดที่กำหนดในระบบ
    """
    user_interfaces = parse_interfaces(user_config)

    missing_keywords = []
    found_keywords = []

    # ตรวจสอบแต่ละ interface
    for keyword in keywords:
        if isinstance(keyword, dict):  # ตรวจสอบแบบบล็อก
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]

            # ตรวจสอบว่ามีบล็อกนี้ใน config ผู้ใช้หรือไม่
            if interface_name in user_interfaces:
                missing = check_interface_block(user_interfaces[interface_name], expected_commands)
                if not missing:
                    found_keywords.append(interface_name)
                else:
                    missing_keywords.extend([f"{interface_name}: {cmd}" for cmd in missing])
            else:
                missing_keywords.append(f"{interface_name}: (missing block)")
        else:  # ตรวจสอบคีย์เวิร์ดทั่วไป
            if any(keyword in line.lower() for line in user_config.splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    # คำนวณคะแนน
    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0

    return score, missing_keywords

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ PC Config
# ----------------------------------------------------------------------
def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway):
    """
    ตรวจสอบค่าของ PC Config ว่าถูกต้องหรือไม่
    """
    correct_ip = "192.168.1.10"
    correct_subnet = "255.255.255.0"
    correct_gateway = "192.168.1.1"

    pc_correct = (
        user_pc_ip == correct_ip and
        user_pc_subnet == correct_subnet and
        user_pc_gateway == correct_gateway
    )
    return pc_correct

# ----------------------------------------------------------------------
# คีย์เวิร์ดสำหรับตรวจสอบ
# ----------------------------------------------------------------------
KEYWORDS = [
    "service password-encryption",
    "hostname s1",
    "no ip domain-lookup",
    {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
    {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0", "ip default-gateway 192.168.1.1"]}
]

# ----------------------------------------------------------------------
# เชื่อมต่อ MongoDB
# ----------------------------------------------------------------------
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab4_scores']

# ----------------------------------------------------------------------
# Route: /lab4
# ----------------------------------------------------------------------
@lab4_bp.route('/lab4')
def lab4():
    return render_template('lab4.html')

@lab4_bp.route('/check_config/lab4', methods=['POST'])
def check_config_lab4():
    # รับค่าจากฟอร์ม
    user_switch_config = request.form.get('config_switch', '').strip()
    user_pc_ip = request.form.get('pc_ip_address', '').strip()
    user_pc_subnet = request.form.get('pc_subnet_mask', '').strip()
    user_pc_gateway = request.form.get('pc_default_gateway', '').strip()

    # ตรวจสอบ PC Config
    pc_correct = check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway)
    pc_status = "ถูกต้อง" if pc_correct else f"ผิดพลาด (IP={user_pc_ip}, Subnet={user_pc_subnet}, Gateway={user_pc_gateway})"

    # ตรวจสอบ Switch Config
    switch_score, missing_keywords = check_keywords(user_switch_config, KEYWORDS)

    # แปลง missing_keywords เป็นข้อความ
    missing_str = "<br><strong>ขาดคอนฟิก:</strong><br>" + "<br>".join(f"- {kw}" for kw in missing_keywords) if missing_keywords else ""

    # เวลาไทย
    try:
        bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))
    except:
        import pytz
        tz = pytz.timezone('Asia/Bangkok')
        bangkok_time = datetime.now(tz)

    # บันทึกลงฐานข้อมูล
    username = session.get('username', 'unknown')
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 4",
        "switch_score": f"{switch_score:.2f}%",
        "pc_status": pc_status,
        "missing_keywords": missing_keywords,
        "timestamp": bangkok_time
    })

    # สร้างผลลัพธ์สำหรับแสดงในหน้าเว็บ
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนน Switch: {switch_score:.2f}%<br>
    PC: {pc_status}<br>
    {missing_str}
    """
    return render_template('lab4.html', result=result)
