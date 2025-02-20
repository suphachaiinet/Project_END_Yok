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

lab_bp = Blueprint('lab', __name__)

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
            if any(keyword in line for line in user_config.lower().splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords

KEYWORDS = [
    "service password-encryption",
    "hostname s1",
    "no ip domain-lookup",
    {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
    {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0", "ip default-gateway 192.168.1.1"]}
]

@lab_bp.route('/lab1', methods=['GET', 'POST'])
def lab1():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
        return redirect(url_for('login'))

    username = session.get('username')
    
    # ดึงข้อมูล user จาก db.users_all
    user = db.users_all.find_one({"username": username})
    first_name = "Unknown"
    last_name = "User"
    
    if user:
        first_name = user.get('first_name', first_name)
        last_name = user.get('last_name', last_name)
    
    # ดึงคะแนน
    user_scores = list(scores_collection.find({"username": username}))
    lab_scores = [0] * 16
    # ดึงคะแนน
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
        username = session.get('username', 'unknown')
        user_switch_config = request.form.get('config_switch', '').strip()

        # PC Config
        user_pc_ip = request.form.get('pc_ip_address', '').strip()
        user_pc_subnet = request.form.get('pc_subnet_mask', '').strip()
        user_pc_gateway = request.form.get('pc_default_gateway', '').strip()

        # ตรวจสอบ Switch Config
        switch_score, missing_keywords = check_keywords(user_switch_config, KEYWORDS)

        # ตรวจสอบ PC Config
        pc_correct = (
            user_pc_ip == "192.168.1.10" and
            user_pc_subnet == "255.255.255.0" and
            user_pc_gateway == "192.168.1.1"
        )

        # สร้าง result dictionary
        result = {
            'student_id': username,
            'first_name': session.get('first_name', 'Unknown'),
            'switch_score': round(switch_score, 2),
            'missing_commands': missing_keywords,
            'pc_status': 'correct' if pc_correct else 'incorrect',
            'status': 'success' if switch_score == 100 and pc_correct else 'partial' if switch_score > 0 or pc_correct else 'failed'
        }

        # บันทึกลงฐานข้อมูลและ session
        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 1"},  # filter
                {"$set": {  # update
                    "switch_score": f"{switch_score:.2f}/100",
                    "pc_status": "ถูกต้อง" if pc_correct else "ไม่ถูกต้อง",
                    "missing_keywords": missing_keywords,
                    "switch_config": user_switch_config,
                    "pc_config": {
                        "ip_address": user_pc_ip,
                        "subnet_mask": user_pc_subnet,
                        "default_gateway": user_pc_gateway
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True  # สร้างเอกสารใหม่หากไม่มี
            )

            # เก็บคะแนนใน session
            session['lab1_score'] = round(switch_score, 2)
            session['lab1_result'] = result
            session.modified = True  # บอกให้ Flask รู้ว่า session ถูกแก้ไข

            print(f"Saved score for {username}: {switch_score}")
        except Exception as e:
            print(f"Error saving score: {e}")

        return redirect(url_for('lab.lab1'))
    
    # กรณี GET
    result = session.get('lab1_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab1.html', 
                     result=result,
                     scores=lab_scores,
                     overall_score=overall_score,
                     first_name=first_name,
                     last_name=last_name,
                     active_lab='lab1')  # เพิ่ม active_lab เพื่อไฮไลท์เมนู