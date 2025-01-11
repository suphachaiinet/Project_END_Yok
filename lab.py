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

lab_bp = Blueprint('lab', __name__)

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
            if any(keyword in line for line in user_config.lower().splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    # คำนวณคะแนน
    total_keywords = len(keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ PC Config
# ----------------------------------------------------------------------
def check_pc_config(pc_config):
    """
    ใช้ Regular Expressions เพื่อตรวจสอบ PC Config
    """
    # ดึงค่าจาก PC Config
    ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', pc_config, re.IGNORECASE)
    gateway_match = re.search(r'ip default-gateway\s+([\d.]+)', pc_config, re.IGNORECASE)

    if ip_match:
        user_pc_ip, user_pc_subnet = ip_match.groups()
    else:
        user_pc_ip, user_pc_subnet = None, None

    if gateway_match:
        user_pc_gateway = gateway_match.group(1)
    else:
        user_pc_gateway = None

    # ตรวจสอบค่าที่ผู้ใช้ส่งมา
    pc_correct = (
        user_pc_ip == "192.168.1.10" and
        user_pc_subnet == "255.255.255.0" and
        user_pc_gateway == "192.168.1.1"
    )

    return pc_correct, user_pc_ip, user_pc_subnet, user_pc_gateway

# ----------------------------------------------------------------------
# คีย์เวิร์ดสำหรับตรวจสอบ (เฉลยบังคับในโค้ด)
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
scores_collection = db['lab_scores']

# ----------------------------------------------------------------------
# Route: /lab1
# ----------------------------------------------------------------------
@lab_bp.route('/lab1')
def lab1():
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1', methods=['POST'])
def check_config_lab1():
    user_switch_config = request.form.get('config_switch', '').strip()

    # อ่านค่าจากฟอร์มสำหรับ PC Config
    user_pc_ip = request.form.get('pc_ip_address', '').strip()
    user_pc_subnet = request.form.get('pc_subnet_mask', '').strip()
    user_pc_gateway = request.form.get('pc_default_gateway', '').strip()

    # ตรวจสอบ PC Config
    pc_correct = (
        user_pc_ip == "192.168.1.10" and
        user_pc_subnet == "255.255.255.0" and
        user_pc_gateway == "192.168.1.1"
    )

    pc_status = "ถูกต้อง" if pc_correct else f"ผิดพลาด "

    # ตรวจสอบ Switch Config ด้วยคีย์เวิร์ด
    switch_score, missing_keywords = check_keywords(user_switch_config, KEYWORDS)

    # แปลง missing_keywords เป็นข้อความ
    missing_str = ""
    if missing_keywords:
        missing_str = "<br><strong>ขาดคอนฟิก:</strong><br>"
        for kw in missing_keywords:
            missing_str += f"- {kw}<br>"

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
        "lab": "Lab 1",
        "switch_score": f"{switch_score:.2f}/100",
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
    return render_template('lab1.html', result=result)
