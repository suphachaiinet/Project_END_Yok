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

lab3_bp = Blueprint('lab3', __name__)

# ----------------------------------------------------------------------
# Function: Parse Interface Blocks
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
# Function: Check Interface Block Commands
# ----------------------------------------------------------------------
def check_interface_block(interface_block, expected_commands):
    missing_commands = [cmd for cmd in expected_commands if cmd not in interface_block]
    return missing_commands

# ----------------------------------------------------------------------
# Function: Check Keywords
# ----------------------------------------------------------------------
def check_keywords(user_config, keywords):
    user_interfaces = parse_interfaces(user_config)

    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):  # Block check
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
        else:  # General keyword check
            if any(keyword in line for line in user_config.splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0

    return score, missing_keywords

# ----------------------------------------------------------------------
# Function: Check PC Configuration
# ----------------------------------------------------------------------
def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway, correct_ip, correct_subnet, correct_gateway):
    return user_pc_ip == correct_ip and user_pc_subnet == correct_subnet and user_pc_gateway == correct_gateway

# ----------------------------------------------------------------------
# Keywords for SW1 and SW2
# ----------------------------------------------------------------------
SW1_KEYWORDS = [
    "hostname S1",
    "no ip domain-lookup",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
]

SW2_KEYWORDS = [
    "hostname S2",
    "no ip domain-lookup",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
]

# ----------------------------------------------------------------------
# MongoDB Connection
# ----------------------------------------------------------------------
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab3_scores']

# ----------------------------------------------------------------------
# Route: /lab3
# ----------------------------------------------------------------------
@lab3_bp.route('/lab3')
def lab3():
    return render_template('lab3.html')

@lab3_bp.route('/check_config/lab3', methods=['POST'])
def check_config_lab3():
    user_sw1_config = request.form.get('config_switch1', '').strip()
    user_sw2_config = request.form.get('config_switch2', '').strip()
    user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
    user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
    user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
    user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
    user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
    user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

    # Check PC Configurations
    pc1_correct = check_pc_config(user_pc1_ip, user_pc1_subnet, user_pc1_gateway, "192.168.1.3", "255.255.255.0", "192.168.1.1")
    pc2_correct = check_pc_config(user_pc2_ip, user_pc2_subnet, user_pc2_gateway, "192.168.1.4", "255.255.255.0", "192.168.1.1")

    # Check Switch Configurations
    sw1_score, sw1_missing_keywords = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing_keywords = check_keywords(user_sw2_config, SW2_KEYWORDS)

    # Calculate Total Score
    total_score = (sw1_score + sw2_score) / 2

    # Format Missing Keywords for Display
    sw1_missing_str = ", ".join(sw1_missing_keywords) if sw1_missing_keywords else "ไม่มี"
    sw2_missing_str = ", ".join(sw2_missing_keywords) if sw2_missing_keywords else "ไม่มี"

    # Timestamp for Submission
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # Save Results to Database
    username = session.get('username', 'unknown')
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 3",
        "sw1_score": f"{sw1_score:.2f}%",
        "sw2_score": f"{sw2_score:.2f}%",
        "total_score": f"{total_score:.2f}%",
        "pc1_status": "ถูกต้อง" if pc1_correct else "ผิดพลาด",
        "pc2_status": "ถูกต้อง" if pc2_correct else "ผิดพลาด",
        "sw1_missing_keywords": sw1_missing_keywords,
        "sw2_missing_keywords": sw2_missing_keywords,
        "timestamp": bangkok_time
    })

    # Generate Result for Display
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนนรวม: {total_score:.2f}%<br>
    SW1: {sw1_score:.2f}% (ขาดคอนฟิก: {sw1_missing_str})<br>
    SW2: {sw2_score:.2f}% (ขาดคอนฟิก: {sw2_missing_str})<br>
    สถานะ PC1: {"ถูกต้อง" if pc1_correct else f"ผิดพลาด (IP={user_pc1_ip}, Subnet={user_pc1_subnet}, Gateway={user_pc1_gateway})"}<br>
    สถานะ PC2: {"ถูกต้อง" if pc2_correct else f"ผิดพลาด (IP={user_pc2_ip}, Subnet={user_pc2_subnet}, Gateway={user_pc2_gateway})"}<br>
    """
    return render_template('lab3.html', result=result)
