import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo  # ใช้สำหรับเวลาประเทศไทย

lab6_bp = Blueprint('lab6', __name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab6_scores']

R1_KEYWORDS = [
    "hostname R1",
    "service password-encryption",
    "no ip domain lookup",
    {"interface GigabitEthernet0/0/1.3": ["description Management Network", "encapsulation dot1Q 3", "ip address 192.168.3.1 255.255.255.0"]},
    {"interface GigabitEthernet0/0/1.4": ["description Operations Network", "encapsulation dot1Q 4", "ip address 192.168.4.1 255.255.255.0"]},
    {"interface GigabitEthernet0/0/1.8": ["description Native VLAN", "encapsulation dot1Q 8 native"]}
]

SW1_KEYWORDS = [
    "hostname S1",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 3", "switchport mode access"]},
    {"interface Vlan3": ["ip address 192.168.3.11 255.255.255.0"]},
    "ip default-gateway 192.168.3.1"
]

SW2_KEYWORDS = [
    "hostname S2",
    "service password-encryption",
    "spanning-tree mode rapid-pvst",
    {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 4", "switchport mode access"]},
    {"interface Vlan3": ["ip address 192.168.3.12 255.255.255.0"]},
    "ip default-gateway 192.168.3.1"
]

def check_keywords(user_config, keywords):
    """
    ตรวจสอบ config ของผู้ใช้ว่ามีคำสั่งครบถ้วนหรือไม่
    """
    user_lines = user_config.splitlines()
    missing_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):  # สำหรับการตรวจสอบบล็อกคำสั่งใน Interface
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]
            block_found = False

            for i, line in enumerate(user_lines):
                if re.match(rf"^\s*{re.escape(interface_name)}\s*$", line.strip()):
                    block_found = True
                    # ค้นหาคำสั่งภายในบล็อก Interface
                    block_content = []
                    for l in user_lines[i + 1:]:
                        if re.match(r"^\s*(interface|!)\s*", l):
                            break
                        block_content.append(l.strip())

                    # ตรวจสอบคำสั่งที่หายไป
                    missing_in_block = [
                        cmd for cmd in expected_commands if not any(cmd in line for line in block_content)
                    ]
                    if missing_in_block:
                        missing_keywords.append(
                            f"{interface_name}: ขาด {', '.join(missing_in_block)}"
                        )
                    break

            if not block_found:
                missing_keywords.append(f"{interface_name}: missing block")

        elif isinstance(keyword, str):  # สำหรับคำสั่งทั่วไป
            keyword_found = any(
                re.search(rf"^\s*{re.escape(keyword)}\s*$", line) for line in user_lines
            )
            if not keyword_found:
                missing_keywords.append(f"{keyword}: missing")

        else:
            raise TypeError(f"Invalid keyword type: {type(keyword)}. Expected str or dict.")

    # คำนวณคะแนน
    score = (len(keywords) - len(missing_keywords)) / len(keywords) * 100
    return score, missing_keywords

def check_vlan_config(vlan_config, expected_vlans):
    missing_vlans = []
    vlan_lines = vlan_config.splitlines()

    for vlan_id, vlan_name in expected_vlans.items():
        found = any(re.match(rf"^{vlan_id}\s+{vlan_name}", line) for line in vlan_lines)
        if not found:
            missing_vlans.append(f"VLAN {vlan_id}: {vlan_name} missing")

    return missing_vlans

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
    return ip == correct_ip and subnet == correct_subnet and gateway == correct_gateway

@lab6_bp.route('/lab6')
def lab6():
    return render_template('lab6.html')

@lab6_bp.route('/check_config/lab6', methods=['POST'])
def check_config_lab6():
    user_r1_config = request.form.get('config_router1', '').strip()
    user_sw1_config = request.form.get('config_sw1', '').strip()
    user_sw2_config = request.form.get('config_sw2', '').strip()
    user_vlan_sw1 = request.form.get('vlan_sw1', '').strip()
    user_vlan_sw2 = request.form.get('vlan_sw2', '').strip()
    pca_ip = request.form.get('pca_ip', '').strip()
    pca_subnet = request.form.get('pca_subnet', '').strip()
    pca_gateway = request.form.get('pca_gateway', '').strip()
    pcb_ip = request.form.get('pcb_ip', '').strip()
    pcb_subnet = request.form.get('pcb_subnet', '').strip()
    pcb_gateway = request.form.get('pcb_gateway', '').strip()

    r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS)
    sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

    vlan_sw1_missing = check_vlan_config(user_vlan_sw1, {"3": "Management", "4": "Operations", "8": "Native"})
    vlan_sw2_missing = check_vlan_config(user_vlan_sw2, {"3": "Management", "4": "Operations", "8": "Native"})

    pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.3.3", "255.255.255.0", "192.168.3.1")
    pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway, "192.168.4.3", "255.255.255.0", "192.168.4.1")

    total_score = (r1_score * 0.3) + (sw1_score * 0.35) + (sw2_score * 0.35)

    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    scores_collection.insert_one({
        "username": session.get('username', 'unknown'),
        "lab": "Lab 6",
        "r1_score": r1_score,
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "vlan_sw1_missing": vlan_sw1_missing,
        "vlan_sw2_missing": vlan_sw2_missing,
        "pca_correct": "ถูกต้อง" if pca_correct else "ผิดพลาด",
        "pcb_correct": "ถูกต้อง" if pcb_correct else "ผิดพลาด",
        "total_score": total_score,
        "timestamp": bangkok_time
    })

    result = f"""
    คะแนนรวม: {total_score:.2f}%<br>
    R1: คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
    SW1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
    SW2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
    VLAN SW1: {"ถูกต้อง" if not vlan_sw1_missing else f"ขาด: {', '.join(vlan_sw1_missing)}"}<br>
    VLAN SW2: {"ถูกต้อง" if not vlan_sw2_missing else f"ขาด: {', '.join(vlan_sw2_missing)}"}<br>
    PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
    PC B: {"ถูกต้อง" if pcb_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    return render_template('lab6.html', result=result)
