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

lab2_bp = Blueprint('lab2', __name__)

# ----------------------------------------------------------------------
# ฟังก์ชันแยกบล็อกของ interface
# ----------------------------------------------------------------------
def parse_interfaces(config_text):
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
    missing_commands = [cmd for cmd in expected_commands if cmd not in interface_block]
    return missing_commands

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบคำสั่ง
# ----------------------------------------------------------------------
def check_keywords(user_config, keywords):
    user_interfaces = parse_interfaces(user_config)

    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):  # ตรวจสอบแบบบล็อก
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]

            if interface_name in user_interfaces:
                missing = check_interface_block(user_interfaces[interface_name], expected_commands)
                if not missing:
                    found_keywords.append(interface_name)
                else:
                    missing_keywords.extend([f"{interface_name}: {cmd}" for cmd in missing])
            else:
                missing_keywords.append(f"{interface_name}: (missing block)")
        else:  # ตรวจสอบคำทั่วไป
            if any(keyword in line for line in user_config.splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0

    return score, missing_keywords

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ PC Config
# ----------------------------------------------------------------------
def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway, correct_ip, correct_subnet, correct_gateway):
    pc_correct = (
        user_pc_ip == correct_ip and
        user_pc_subnet == correct_subnet and
        user_pc_gateway == correct_gateway
    )
    return pc_correct

# ----------------------------------------------------------------------
# คีย์เวิร์ดสำหรับตรวจสอบ Switch Config
# ----------------------------------------------------------------------
SW1_KEYWORDS = [
    "hostname S1",
    "no ip domain-lookup",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]},

]

SW2_KEYWORDS = [
    "hostname S2",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]},
    
]

# ----------------------------------------------------------------------
# เชื่อมต่อ MongoDB
# ----------------------------------------------------------------------
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab2_scores']

# ----------------------------------------------------------------------
# Route: /lab2
# ----------------------------------------------------------------------
@lab2_bp.route('/lab2')
def lab2():
    return render_template('lab2.html')

@lab2_bp.route('/check_config/lab2', methods=['POST'])
def check_config_lab2():
    # รับค่าจากฟอร์ม
    user_sw1_config = request.form.get('config_switch1', '').strip()
    user_sw2_config = request.form.get('config_switch2', '').strip()
    user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
    user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
    user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
    user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
    user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
    user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

    # ตรวจสอบ PC Config
    pc1_correct = check_pc_config(user_pc1_ip, user_pc1_subnet, user_pc1_gateway, "192.168.10.3", "255.255.255.0", "192.168.10.1")
    pc2_correct = check_pc_config(user_pc2_ip, user_pc2_subnet, user_pc2_gateway, "192.168.10.4", "255.255.255.0", "192.168.10.1")

    # ตรวจสอบ Switch Config
    sw1_score, sw1_missing_keywords = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing_keywords = check_keywords(user_sw2_config, SW2_KEYWORDS)

    # คำนวณคะแนนรวม SW1 และ SW2
    total_switch_score = (sw1_score + sw2_score) / 2

    # เวลาปัจจุบันตามโซนเวลาไทย
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # บันทึกลงฐานข้อมูล
    username = session.get('username', 'unknown')
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 2",
        "sw1_score": f"{sw1_score:.2f}%",
        "sw2_score": f"{sw2_score:.2f}%",
        "total_switch_score": f"{total_switch_score:.2f}%",
        "pc1_status": "ถูกต้อง" if pc1_correct else "ผิดพลาด",
        "pc2_status": "ถูกต้อง" if pc2_correct else "ผิดพลาด",
        "sw1_missing_keywords": sw1_missing_keywords,
        "sw2_missing_keywords": sw2_missing_keywords,
        "timestamp": bangkok_time
    })

    # สร้างข้อความแสดงขาดคอนฟิก (เฉพาะกรณีมีคำสั่งขาด)
    sw1_missing_str = f"ขาดคอนฟิก SW1: {', '.join(sw1_missing_keywords)}<br>" if sw1_missing_keywords else ""
    sw2_missing_str = f"ขาดคอนฟิก SW2: {', '.join(sw2_missing_keywords)}<br>" if sw2_missing_keywords else ""

    # ผลลัพธ์ที่จะส่งไปแสดง
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนน SW1: {sw1_score:.2f}%<br>
    คะแนน SW2: {sw2_score:.2f}%<br>
    คะแนนรวม Switch (SW1 + SW2): {total_switch_score:.2f}%<br>
    {sw1_missing_str}
    {sw2_missing_str}
    สถานะ PC1: {"ถูกต้อง" if pc1_correct else f"ผิดพลาด (IP={user_pc1_ip}, Subnet={user_pc1_subnet}, Gateway={user_pc1_gateway})"}<br>
    สถานะ PC2: {"ถูกต้อง" if pc2_correct else f"ผิดพลาด (IP={user_pc2_ip}, Subnet={user_pc2_subnet}, Gateway={user_pc2_gateway})"}<br>
    """
    return render_template('lab2.html', result=result)
