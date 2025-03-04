import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab15_bp = Blueprint('lab15', __name__)

# MongoDB Connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']

def check_keywords(user_config, keywords):
    """Check if configuration contains required keywords"""
    user_lines = user_config.splitlines()
    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]
            block_found = False

            for i, line in enumerate(user_lines):
                if re.match(rf"^\s*{re.escape(interface_name)}\s*$", line.strip()):
                    block_found = True
                    block_content = []
                    for l in user_lines[i + 1:]:
                        if re.match(r"^\s*(interface|!|router|ip route)\s*", l):
                            break
                        block_content.append(l.strip())

                    missing_in_block = [
                        cmd for cmd in expected_commands if not any(cmd in line for line in block_content)
                    ]
                    if missing_in_block:
                        missing_keywords.append(
                            f"{interface_name}: ขาด {', '.join(missing_in_block)}"
                        )
                    else:
                        found_keywords.append(interface_name)
                    break

            if not block_found:
                missing_keywords.append(f"{interface_name}: missing block")

        elif isinstance(keyword, str):
            keyword_found = any(
                re.search(rf"^\s*{re.escape(keyword)}\s*", line) for line in user_lines
            )
            if keyword_found:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(f"{keyword}: missing")

    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0
    return score, missing_keywords

def check_simple_pc_config(ip, subnet, gateway):
    """ตรวจสอบอย่างง่ายว่า PC config มีรูปแบบถูกต้องหรือไม่"""
    try:
        # ตรวจสอบว่ามีการใส่ค่าครบทุกส่วน
        if not ip or not subnet or not gateway:
            return False
            
        # ตรวจสอบว่า IP, subnet และ gateway มีรูปแบบถูกต้อง
        ip_parts = ip.split('.')
        subnet_parts = subnet.split('.')
        gateway_parts = gateway.split('.')
        
        # ตรวจสอบว่ามี 4 ส่วนที่แยกด้วยจุด
        if len(ip_parts) != 4 or len(subnet_parts) != 4 or len(gateway_parts) != 4:
            return False
            
        # ถ้าผ่านการตรวจสอบเบื้องต้น ถือว่าถูกต้อง
        return True
    except:
        return False

# Keywords for checking Router configurations
R1_KEYWORDS = [
    "hostname R1",
    "no ip domain lookup",
    {"interface GigabitEthernet0/1": [
        "ip address 192.168.1.1 255.255.255.0",
        "standby version 2",
        "standby 1 ip 192.168.1.254",
        "standby 1 priority 150",
        "standby 1 preempt"
    ]},
    {"interface Serial0/0/0": [
        "ip address 10.1.1.1 255.255.255.252",
        "clock rate 128000"
    ]},
    {"router rip": [
        "network 10.1.1.0",
        "network 192.168.1.0"
    ]}
]

R2_KEYWORDS = [
    "hostname R2",
    "no ip domain lookup",
    {"interface Loopback1": [
        "ip address 209.165.200.225 255.255.255.224"
    ]},
    {"interface Serial0/0/0": [
        "ip address 10.1.1.2 255.255.255.252"
    ]},
    {"interface Serial0/0/1": [
        "ip address 10.2.2.2 255.255.255.252",
        "clock rate 128000"
    ]},
    {"router rip": [
        "network 10.1.1.0",
        "network 10.2.2.0",
        "default-information originate"
    ]},
    "ip route 0.0.0.0 0.0.0.0 Loopback1"
]

R3_KEYWORDS = [
    "hostname R3",
    "no ip domain lookup",
    {"interface GigabitEthernet0/1": [
        "ip address 192.168.1.3 255.255.255.0",
        "standby version 2", 
        "standby 1 ip 192.168.1.254",
        "standby 1 priority 200",
        "standby 1 preempt"
    ]},
    {"interface Serial0/0/1": [
        "ip address 10.2.2.1 255.255.255.252"
    ]},
    {"router rip": [
        "network 10.2.2.0",
        "network 192.168.1.0"
    ]}
]

# Keywords for checking Switch configurations
SW1_KEYWORDS = [
    "hostname S1",
    "no ip domain-lookup",
    {"interface Vlan1": [
        "ip address 192.168.1.11 255.255.255.0"
    ]},
    "ip default-gateway 192.168.1.254"
]

SW2_KEYWORDS = [
    "hostname S3",
    "no ip domain-lookup",
    "spanning-tree mode pvst",
    {"interface Vlan1": [
        "ip address 192.168.1.13 255.255.255.0"
    ]},
    "ip default-gateway 192.168.1.254"
]

@lab15_bp.route('/lab15', methods=['GET', 'POST'])
def lab15():
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
    
    for score_entry in user_scores:
        try:
            lab_num = int(score_entry['lab'].replace('Lab ', '')) - 1
            score = float(score_entry['switch_score'].split('/')[0])
            lab_scores[lab_num] = score
        except Exception as e:
            print(f"Error processing score: {e}")
    
    overall_score = sum(lab_scores) / 16

    if request.method == 'POST':
        # Get configurations from form
        user_r1_config = request.form.get('config_r1', '').strip()
        user_r2_config = request.form.get('config_r2', '').strip()
        user_r3_config = request.form.get('config_r3', '').strip()
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw2_config = request.form.get('config_sw2', '').strip()
        
        # Get PC configurations
        pc_a_ip = request.form.get('pc_a_ip', '').strip()
        pc_a_subnet = request.form.get('pc_a_subnet', '').strip()
        pc_a_gateway = request.form.get('pc_a_gateway', '').strip()
        
        pc_c_ip = request.form.get('pc_c_ip', '').strip()
        pc_c_subnet = request.form.get('pc_c_subnet', '').strip()
        pc_c_gateway = request.form.get('pc_c_gateway', '').strip()

        # Check devices configurations
        r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS)
        r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
        r3_score, r3_missing = check_keywords(user_r3_config, R3_KEYWORDS)
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        # แก้ไขการเช็ค PC - เช็คแค่ว่าค่าที่ใส่มีรูปแบบถูกต้องหรือไม่
        pc_a_correct = check_simple_pc_config(pc_a_ip, pc_a_subnet, pc_a_gateway)
        pc_c_correct = check_simple_pc_config(pc_c_ip, pc_c_subnet, pc_c_gateway)

        # คำนวณคะแนนแบบง่าย - ทุก keyword มีค่าเท่ากัน
        # นับจำนวน keyword ทั้งหมดที่ถูกต้อง
        total_keywords = len(R1_KEYWORDS) + len(R2_KEYWORDS) + len(R3_KEYWORDS) + len(SW1_KEYWORDS) + len(SW2_KEYWORDS) + 2  # +2 for PC configs
        found_keywords = (
            len(R1_KEYWORDS) - len(r1_missing) +
            len(R2_KEYWORDS) - len(r2_missing) +
            len(R3_KEYWORDS) - len(r3_missing) +
            len(SW1_KEYWORDS) - len(sw1_missing) +
            len(SW2_KEYWORDS) - len(sw2_missing) +
            (1 if pc_a_correct else 0) +
            (1 if pc_c_correct else 0)
        )
        
        # คำนวณคะแนนเป็นเปอร์เซ็นต์
        total_score = (found_keywords / total_keywords) * 100 if total_keywords > 0 else 0

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'r1_score': round(r1_score, 2),
            'r2_score': round(r2_score, 2),
            'r3_score': round(r3_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'r1_missing': r1_missing,
            'r2_missing': r2_missing,
            'r3_missing': r3_missing,
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'pca_status': 'correct' if pc_a_correct else 'incorrect',
            'pcc_status': 'correct' if pc_c_correct else 'incorrect',
            'status': 'success' if total_score >= 60 else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 15"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "r3_score": f"{r3_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pc_a_correct": "ถูกต้อง" if pc_a_correct else "ไม่ถูกต้อง",
                    "pc_c_correct": "ถูกต้อง" if pc_c_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "r2_config": user_r2_config,
                        "r3_config": user_r3_config,
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "pca_config": {
                            "ip": pc_a_ip,
                            "subnet": pc_a_subnet,
                            "gateway": pc_a_gateway
                        },
                        "pcc_config": {
                            "ip": pc_c_ip,
                            "subnet": pc_c_subnet,
                            "gateway": pc_c_gateway
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
            session['lab15_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab15.lab15'))

    result = session.get('lab15_result')

    return render_template('lab15.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab15')