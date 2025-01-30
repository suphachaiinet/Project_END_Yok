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
# Function: Preprocess VLAN Config (Remove Spaces and Combine Lines)
# ----------------------------------------------------------------------
def preprocess_vlan_config(vlan_config):
    lines = vlan_config.splitlines()
    processed_lines = []
    current_line = ""

    for line in lines:
        if line.strip():  # Skip empty lines
            if re.match(r"^\d+\s+\w+", line):  # Check if line starts with VLAN ID
                if current_line:  # Add previous line to processed lines
                    processed_lines.append(current_line)
                current_line = line.strip()
            else:
                current_line += " " + line.strip()  # Append continuation lines
    if current_line:  # Add the last processed line
        processed_lines.append(current_line)

    return "\n".join(processed_lines)

# ----------------------------------------------------------------------
# Function: Check VLAN Configuration
# ----------------------------------------------------------------------
def check_vlan_config(vlan_config, expected_vlans):
    missing_vlans = []
    incorrect_vlans = {}

    # Preprocess the VLAN configuration to combine lines
    vlan_config = preprocess_vlan_config(vlan_config)

    # Process each expected VLAN
    for vlan_id, expected_data in expected_vlans.items():
        vlan_info = re.search(
            rf"^{vlan_id}\s+(\w+(?:-\w+)?)\s+active\s+([\s\S]*?)(?=^\d+|\Z)",
            vlan_config,
            re.MULTILINE
        )
        if not vlan_info:
            missing_vlans.append(vlan_id)
        else:
            vlan_name = vlan_info.group(1)
            vlan_ports = re.findall(r"(Fa0/\d+|Gig0/\d+)", vlan_info.group(2) if vlan_info.group(2) else "")

            # Compare VLAN name
            if vlan_name != expected_data["name"]:
                incorrect_vlans[vlan_id] = {
                    "type": "name",
                    "expected": expected_data["name"],
                    "actual": vlan_name
                }

            # Compare VLAN ports
            if set(vlan_ports) != set(expected_data["ports"]):
                incorrect_vlans[vlan_id] = {
                    "type": "ports",
                    "expected_ports": expected_data["ports"],
                    "actual_ports": vlan_ports
                }

    return missing_vlans, incorrect_vlans

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
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
    {"interface Vlan20": ["ip address 192.168.20.11 255.255.255.0"]},
    {"interface Vlan30": ["ip address 192.168.30.11 255.255.255.0"]}
]

SW2_KEYWORDS = [
    "hostname S2",
    "no ip domain-lookup",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 30", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]}
]

expected_vlans_sw1 = {
    "1": {"name": "default", "ports": []},
    "10": {"name": "Management", "ports": []},
    "20": {"name": "Sales", "ports": ["Fa0/6"]},
    "30": {"name": "Operations", "ports": []},
    "999": {"name": "ParkingLot", "ports": ["Fa0/2", "Fa0/3", "Fa0/4", "Fa0/5", "Fa0/7", "Fa0/8", "Fa0/9", "Fa0/10", "Fa0/11", "Fa0/12", "Fa0/13", "Fa0/14", "Fa0/15", "Fa0/16", "Fa0/17", "Fa0/18", "Fa0/19", "Fa0/20", "Fa0/21", "Fa0/22", "Fa0/23", "Fa0/24", "Gig0/1", "Gig0/2"]},
    "1000": {"name": "Native", "ports": []}
}

expected_vlans_sw2 = {
    "1": {"name": "default", "ports": []},
    "10": {"name": "Management", "ports": []},
    "20": {"name": "Sales", "ports": []},
    "30": {"name": "Operations", "ports": ["Fa0/18"]},
    "999": {"name": "ParkingLot", "ports": ["Fa0/2", "Fa0/3", "Fa0/4", "Fa0/5", "Fa0/6", "Fa0/7", "Fa0/8", "Fa0/9", "Fa0/10", "Fa0/11", "Fa0/12", "Fa0/13", "Fa0/14", "Fa0/15", "Fa0/16", "Fa0/17", "Fa0/19", "Fa0/20", "Fa0/21", "Fa0/22", "Fa0/23", "Fa0/24", "Gig0/1", "Gig0/2"]}
}

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
    vlan_config_sw1 = request.form.get('vlan_config_switch1', '').strip()
    user_sw2_config = request.form.get('config_switch2', '').strip()
    vlan_config_sw2 = request.form.get('vlan_config_switch2', '').strip()
    user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
    user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
    user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
    user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
    user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
    user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

    # Check PC Configurations
    pc1_correct = check_pc_config(user_pc1_ip, user_pc1_subnet, user_pc1_gateway, "192.168.20.13", "255.255.255.0", "192.168.20.11")
    pc2_correct = check_pc_config(user_pc2_ip, user_pc2_subnet, user_pc2_gateway, "192.168.30.13", "255.255.255.0", "192.168.30.11")

    # Check Switch Configurations
    sw1_score, sw1_missing_keywords = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing_keywords = check_keywords(user_sw2_config, SW2_KEYWORDS)

    # Check VLAN Configurations
    missing_vlans_sw1, incorrect_vlans_sw1 = check_vlan_config(vlan_config_sw1, expected_vlans_sw1)
    missing_vlans_sw2, incorrect_vlans_sw2 = check_vlan_config(vlan_config_sw2, expected_vlans_sw2)

    vlan_status_sw1 = "ถูกต้อง" if not missing_vlans_sw1 and not incorrect_vlans_sw1 else "ผิดพลาด"
    vlan_status_sw2 = "ถูกต้อง" if not missing_vlans_sw2 and not incorrect_vlans_sw2 else "ผิดพลาด"

    # VLAN details for SW1
    vlan_details_sw1 = ""
    if missing_vlans_sw1:
        vlan_details_sw1 += f"ขาด VLAN: {', '.join(missing_vlans_sw1)}<br>"
    if incorrect_vlans_sw1:
        for vlan_id, error in incorrect_vlans_sw1.items():
            if error["type"] == "name":
                vlan_details_sw1 += f"VLAN {vlan_id}: ชื่อผิด (คาดว่า: {error['expected']} แต่ได้: {error['actual']})<br>"
            elif error["type"] == "ports":
                vlan_details_sw1 += f"VLAN {vlan_id}: พอร์ตผิด (คาดว่า: {', '.join(error['expected_ports'])} แต่ได้: {', '.join(error['actual_ports'])})<br>"

    # VLAN details for SW2
    vlan_details_sw2 = ""
    if missing_vlans_sw2:
        vlan_details_sw2 += f"ขาด VLAN: {', '.join(missing_vlans_sw2)}<br>"
    if incorrect_vlans_sw2:
        for vlan_id, error in incorrect_vlans_sw2.items():
            if error["type"] == "name":
                vlan_details_sw2 += f"VLAN {vlan_id}: ชื่อผิด (คาดว่า: {error['expected']} แต่ได้: {error['actual']})<br>"
            elif error["type"] == "ports":
                vlan_details_sw2 += f"VLAN {vlan_id}: พอร์ตผิด (คาดว่า: {', '.join(error['expected_ports'])} แต่ได้: {', '.join(error['actual_ports'])})<br>"

    # Missing configurations for SW1 and SW2
    missing_config_sw1 = "<br>".join(sw1_missing_keywords)
    missing_config_sw2 = "<br>".join(sw2_missing_keywords)

    # Calculate Total Score
    total_score = (sw1_score + sw2_score) / 2

    # Generate Result for Display
    result = f"""
    ชื่อผู้ใช้: {session.get('username', 'unknown')}<br>
    คะแนนรวม: {total_score:.2f}%<br>
    SW1: {sw1_score:.2f}%<br>
    SW2: {sw2_score:.2f}%<br>
    VLAN SW1: {vlan_status_sw1}<br>
    {vlan_details_sw1 if vlan_status_sw1 == "ผิดพลาด" else ""}<br>
    VLAN SW2: {vlan_status_sw2}<br>
    {vlan_details_sw2 if vlan_status_sw2 == "ผิดพลาด" else ""}<br>
    สถานะ PC1: {"ถูกต้อง" if pc1_correct else "ผิดพลาด"}<br>
    สถานะ PC2: {"ถูกต้อง" if pc2_correct else "ผิดพลาด"}<br>
    <br>
    ข้อความตั้งค่าที่ขาดหาย:<br>
    SW1:<br>{missing_config_sw1 if missing_config_sw1 else "ไม่มี"}<br>
    SW2:<br>{missing_config_sw2 if missing_config_sw2 else "ไม่มี"}<br>
    """

    # Save Result to MongoDB
    username = session.get('username', 'unknown')
    scores_collection.insert_one({
        "username": username,
        "total_score": total_score,
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "pc1_status": "ถูกต้อง" if pc1_correct else "ผิดพลาด",
        "pc2_status": "ถูกต้อง" if pc2_correct else "ผิดพลาด",
        "vlan_sw1_status": vlan_status_sw1,
        "vlan_sw2_status": vlan_status_sw2,
        "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
    })

    return render_template('lab3.html', result=result)
