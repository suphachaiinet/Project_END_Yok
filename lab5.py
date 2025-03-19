import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime, timedelta
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab5_bp = Blueprint('lab5', __name__)

# แก้ไขในส่วน MongoDB Connection ของ lab.py
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']
users_collection = db['users_all']  # เพิ่มบรรทัดนี้ให้ชัดเจน

def check_keywords(user_config, keywords):
    """
    ตรวจสอบว่า config ของผู้ใช้มีคำสั่งครบถ้วนตามที่กำหนดใน Key Words
    """
    user_lines = user_config.splitlines()
    missing_keywords = []
    found_keywords = []

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
                        for l in user_lines[user_lines.index(line) + 1:]
                        if not l.startswith("!")
                    ]
                    missing_commands = [
                        cmd for cmd in expected_commands if cmd not in block_content
                    ]
                    if missing_commands:
                        missing_keywords.append(
                            f"{interface_name}: {', '.join(missing_commands)}"
                        )
                    else:
                        found_keywords.append(interface_name)
                    break

            if not found_block:
                missing_keywords.append(f"{interface_name}: missing block")
        else:  # ตรวจสอบคำสั่งทั่วไป
            if any(keyword in line for line in user_lines):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0
    return score, missing_keywords

# Expected configurations
SW1_KEYWORDS = [
    "hostname S1",
    "spanning-tree mode rapid-pvst",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
    {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access", 
                                  "spanning-tree portfast", "spanning-tree bpduguard enable"]},
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

@lab5_bp.route('/lab5', methods=['GET', 'POST'])
def lab5():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
        return redirect(url_for('login'))

    username = session.get('username')
    user_scores = list(scores_collection.find({"username": username}))
    
    lab_scores = [0] * 16
    for score_entry in user_scores:
        try:
            lab_num = int(score_entry['lab'].replace('Lab ', '')) - 1
            score = float(score_entry['switch_score'].split('/')[0])
            lab_scores[lab_num] = score
        except Exception as e:
            print(f"Error processing score: {e}")
    
    overall_score = sum(lab_scores) / 16

    if request.method == 'POST':
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw2_config = request.form.get('config_sw2', '').strip()
        user_sw3_config = request.form.get('config_sw3', '').strip()
        user_pca_ip = request.form.get('pca_ip', '').strip()
        user_pca_subnet = request.form.get('pca_subnet', '').strip()
        user_pcc_ip = request.form.get('pcc_ip', '').strip()
        user_pcc_subnet = request.form.get('pcc_subnet', '').strip()

        # Check configurations
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)
        sw3_score, sw3_missing = check_keywords(user_sw3_config, SW3_KEYWORDS)

        # Check PC configurations
        pca_correct = user_pca_ip == "192.168.0.2" and user_pca_subnet == "255.255.255.0"
        pcc_correct = user_pcc_ip == "192.168.0.3" and user_pcc_subnet == "255.255.255.0"

        # Calculate total score
        total_score = (sw1_score + sw2_score + sw3_score) / 3

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'sw3_score': round(sw3_score, 2),
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'sw3_missing': sw3_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcc_status': 'correct' if pcc_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcc_correct) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 5"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "sw3_score": f"{sw3_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcc_status": "ถูกต้อง" if pcc_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "sw3_config": user_sw3_config,
                        "pca_config": {
                            "ip": user_pca_ip,
                            "subnet": user_pca_subnet
                        },
                        "pcc_config": {
                            "ip": user_pcc_ip,
                            "subnet": user_pcc_subnet
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))+ timedelta(hours=7)
                }},
                upsert=True
            )
            
            session['lab5_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab5.lab5'))

    # สำหรับ GET request
    result = session.get('lab5_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab5.html', 
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                         active_lab='lab5')