import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab2_bp = Blueprint('lab2', __name__)

# แก้ไขในส่วน MongoDB Connection ของ lab.py
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']
users_collection = db['users_all']  # เพิ่มบรรทัดนี้ให้ชัดเจน

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

def check_interface_block(interface_block, expected_commands):
    missing_commands = [cmd for cmd in expected_commands if cmd not in interface_block]
    return missing_commands

def check_keywords(user_config, keywords):
    user_interfaces = parse_interfaces(user_config)
    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):
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
        else:
            if any(keyword in line for line in user_config.splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords

def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway, correct_ip, correct_subnet, correct_gateway):
    pc_correct = (
        user_pc_ip == correct_ip and
        user_pc_subnet == correct_subnet and
        user_pc_gateway == correct_gateway
    )
    return pc_correct

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
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
]

@lab2_bp.route('/lab2', methods=['GET', 'POST'])
def lab2():
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
        user_sw1_config = request.form.get('config_switch1', '').strip()
        user_sw2_config = request.form.get('config_switch2', '').strip()
        
        user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
        user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
        user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
        
        user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
        user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
        user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

        # ตรวจสอบ configurations
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)
        
        pc1_correct = check_pc_config(
            user_pc1_ip, user_pc1_subnet, user_pc1_gateway,
            "192.168.10.3", "255.255.255.0", "192.168.10.1"
        )
        
        pc2_correct = check_pc_config(
            user_pc2_ip, user_pc2_subnet, user_pc2_gateway,
            "192.168.10.4", "255.255.255.0", "192.168.10.1"
        )

        # คำนวณคะแนนรวม
        total_score = (sw1_score + sw2_score) / 2

        # สร้าง result object
        result = {
            'student_id': username,
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'total_score': round(total_score, 2),
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'pc1_status': 'correct' if pc1_correct else 'incorrect',
            'pc2_status': 'correct' if pc2_correct else 'incorrect',
            'status': 'success' if total_score == 100 and pc1_correct and pc2_correct else 'partial'
        }

        # บันทึกลงฐานข้อมูล
        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 2"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pc1_status": "ถูกต้อง" if pc1_correct else "ไม่ถูกต้อง",
                    "pc2_status": "ถูกต้อง" if pc2_correct else "ไม่ถูกต้อง",
                    "sw1_missing": sw1_missing,
                    "sw2_missing": sw2_missing,
                    "configs": {
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "pc1_config": {
                            "ip": user_pc1_ip,
                            "subnet": user_pc1_subnet,
                            "gateway": user_pc1_gateway
                        },
                        "pc2_config": {
                            "ip": user_pc2_ip,
                            "subnet": user_pc2_subnet,
                            "gateway": user_pc2_gateway
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
            session['lab2_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab2.lab2'))

    # สำหรับ GET request
    result = session.get('lab2_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab2.html',
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                         active_lab='lab2')