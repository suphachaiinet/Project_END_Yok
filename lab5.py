import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab5_bp = Blueprint('lab5', __name__)

CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

def check_keywords(user_config, keywords):
    """
    ตรวจสอบว่า config ของผู้ใช้มีคำสั่งครบถ้วนตามที่กำหนดใน Key Words
    """
    user_lines = user_config.splitlines()
    missing_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):  # ตรวจสอบบล็อก
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]
            found_block = False

            for line in user_lines:
                if interface_name in line:
                    found_block = True
                    block_content = [
                        l.strip()
                        for l in user_lines[user_lines.index(line) + 1 : ]
                        if not l.startswith("!")
                    ]
                    missing_commands = [
                        cmd for cmd in expected_commands if cmd not in block_content
                    ]
                    if missing_commands:
                        missing_keywords.append(
                            f"{interface_name}: {', '.join(missing_commands)}"
                        )
                    break

            if not found_block:
                missing_keywords.append(f"{interface_name}: missing block")
        else:  # ตรวจสอบคำสั่งทั่วไป
            if not any(keyword in line for line in user_lines):
                missing_keywords.append(keyword)

    score = (len(keywords) - len(missing_keywords)) / len(keywords) * 100
    return score, missing_keywords

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab5_scores']

@lab5_bp.route('/lab5')
def lab5():
    return render_template('lab5.html')

@lab5_bp.route('/check_config/lab5', methods=['POST'])
def check_config_lab5():
    # รับค่าจากฟอร์ม
    user_sw1_config = request.form.get('config_sw1', '').strip()
    user_sw2_config = request.form.get('config_sw2', '').strip()
    user_sw3_config = request.form.get('config_sw3', '').strip()
    user_pca_ip = request.form.get('pca_ip', '').strip()
    user_pca_subnet = request.form.get('pca_subnet', '').strip()
    user_pcc_ip = request.form.get('pcc_ip', '').strip()
    user_pcc_subnet = request.form.get('pcc_subnet', '').strip()

    # คำสั่ง Key Words
    SW1_KEYWORDS = [
        "hostname S1",
        "spanning-tree mode rapid-pvst",
        {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access", "spanning-tree portfast", "spanning-tree bpduguard enable"]},
        {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
    ]
    SW2_KEYWORDS = [
        "hostname S2",
        "spanning-tree mode rapid-pvst",
        {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
    ]
    SW3_KEYWORDS = [
        "hostname S3",
        "spanning-tree mode rapid-pvst",
        "spanning-tree portfast default",
        "spanning-tree portfast bpduguard default",
        {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
        {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
        {"interface Vlan99": ["ip address 192.168.1.13 255.255.255.0"]}
    ]

    # ตรวจสอบ Switch Config
    sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)
    sw3_score, sw3_missing = check_keywords(user_sw3_config, SW3_KEYWORDS)

    # ตรวจสอบ PC Config
    pca_correct = user_pca_ip == "192.168.0.2" and user_pca_subnet == "255.255.255.0"
    pcc_correct = user_pcc_ip == "192.168.0.3" and user_pcc_subnet == "255.255.255.0"

    # ดึง username และเวลาปัจจุบัน
    username = session.get('username', 'unknown')
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # บันทึกลง MongoDB
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 5",
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "sw3_score": sw3_score,
        "pca_status": "ถูกต้อง" if pca_correct else "ผิดพลาด",
        "pcc_status": "ถูกต้อง" if pcc_correct else "ผิดพลาด",
        "timestamp": bangkok_time
    })

    # ผลลัพธ์สำหรับแสดงผล
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    SW1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
    SW2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
    SW3: คะแนน {sw3_score:.2f}% ({'ถูกต้อง' if not sw3_missing else f"ขาด: {', '.join(sw3_missing)}"})<br>
    PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด (IP: {user_pca_ip}, Subnet: {user_pca_subnet})"}<br>
    PC C: {"ถูกต้อง" if pcc_correct else "ผิดพลาด (IP: {user_pcc_ip}, Subnet: {user_pcc_subnet})"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """
    return render_template('lab5.html', result=result)
