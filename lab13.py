import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime , timedelta
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab13_bp = Blueprint('lab13', __name__)

# MongoDB Connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']

def check_keywords(user_config, keywords):
    user_lines = user_config.splitlines()
    missing_keywords = []
    found_keywords = []

    # สร้าง dictionary เก็บบล็อกต่างๆ
    config_blocks = {}
    current_block = None
    block_content = []

    for line in user_lines:
        line = line.strip()
        if not line or line == '!':
            if current_block:
                config_blocks[current_block] = block_content
                current_block = None
                block_content = []
            continue
        
        if line.startswith('interface ') or line.startswith('ipv6 dhcp pool '):
            # เริ่มบล็อกใหม่
            if current_block:
                config_blocks[current_block] = block_content
            current_block = line
            block_content = []
        elif current_block:
            # เพิ่มเนื้อหาเข้าบล็อก
            block_content.append(line)
    
    # เก็บบล็อกสุดท้าย (ถ้ามี)
    if current_block:
        config_blocks[current_block] = block_content

    # ตรวจสอบคีย์เวิร์ด
    for keyword in keywords:
        if isinstance(keyword, dict):
            block_name = list(keyword.keys())[0]
            expected_commands = keyword[block_name]
            
            # ตรวจสอบว่ามีบล็อกนี้หรือไม่
            block_found = False
            for config_block in config_blocks.keys():
                if block_name in config_block:
                    block_found = True
                    block_content = config_blocks[config_block]
                    
                    # ตรวจสอบคำสั่งในบล็อก
                    missing_commands = []
                    for cmd in expected_commands:
                        cmd_found = False
                        for content in block_content:
                            if cmd.lower() in content.lower():
                                cmd_found = True
                                break
                        
                        if not cmd_found:
                            missing_commands.append(cmd)
                    
                    if missing_commands:
                        missing_keywords.append(f"{block_name}: ขาด {', '.join(missing_commands)}")
                    else:
                        found_keywords.append(block_name)
                    break
            
            if not block_found:
                missing_keywords.append(f"{block_name}: missing block")
        
        else:  # คีย์เวิร์ดปกติ
            keyword_found = False
            for line in user_lines:
                if keyword.lower() in line.lower():
                    keyword_found = True
                    break
            
            if keyword_found:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(f"{keyword}: missing")
    
    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0
    return score, missing_keywords

def check_pc_config(ip, subnet, correct_ip_prefix):
    return ip.lower().startswith(correct_ip_prefix.lower())

# Expected configurations
R1_KEYWORDS = [
   "hostname R1",
   "service password-encryption",
   "ipv6 unicast-routing",
   {"ipv6 dhcp pool R1-STATELESS": [
       "dns-server 2001:DB8:ACAD::254",
       "domain-name STATELESS.com"
   ]},
   {"ipv6 dhcp pool R2-STATEFUL": [
       "address prefix 2001:DB8:ACAD:3:AAAA::/80",
       "dns-server 2001:DB8:ACAD::254",
       "domain-name STATEFUL.com"
   ]},
   {"interface GigabitEthernet0/0/0": [
       "ipv6 address 2001:DB8:ACAD:2::1/64",
       "ipv6 address FE80::1 link-local",
       "ipv6 dhcp server R2-STATEFUL"
   ]},
   {"interface GigabitEthernet0/0/1": [
       "ipv6 address 2001:DB8:ACAD:1::1/64",
       "ipv6 address FE80::1 link-local",
       "ipv6 nd other-config-flag",
       "ipv6 dhcp server R1-STATELESS"
   ]},
   "ipv6 route ::/0 2001:DB8:ACAD:2::2"
]

R2_KEYWORDS = [
   "hostname R2",
   "service password-encryption",
   "ipv6 unicast-routing",
   {"interface GigabitEthernet0/0/0": [
       "ipv6 address 2001:DB8:ACAD:2::2/64",
       "ipv6 address FE80::2 link-local"
   ]},
   {"interface GigabitEthernet0/0/1": [
       "ipv6 address 2001:DB8:ACAD:3::1/64",
       "ipv6 address FE80::2 link-local",
       "ipv6 nd prefix 2001:DB8:ACAD:3::/64 2592000 604800 no-autoconfig",
       "ipv6 nd managed-config-flag",
       "ipv6 dhcp relay destination 2001:DB8:ACAD:2::1 GigabitEthernet0/0/0"
   ]},
   "ipv6 route ::/0 2001:DB8:ACAD:2::1"
]

SW1_KEYWORDS = [
   "hostname S1",
   "service password-encryption",
   "spanning-tree mode pvst"
]

SW2_KEYWORDS = [
   "hostname S2",
   "service password-encryption", 
   "spanning-tree mode pvst"
]

@lab13_bp.route('/lab13', methods=['GET', 'POST'])
def lab13():
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
        user_r1_config = request.form.get('config_r1', '').strip()
        user_r2_config = request.form.get('config_r2', '').strip()
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw2_config = request.form.get('config_sw2', '').strip()
        
        pca_ip = request.form.get('pca_ip', '').strip()
        pca_subnet = request.form.get('pca_subnet', '').strip() 
        
        pcb_ip = request.form.get('pcb_ip', '').strip()
        pcb_subnet = request.form.get('pcb_subnet', '').strip()

        # Check configurations
        r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS) 
        r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, "2001:db8:acad:1:")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, "2001:db8:acad:3:")

        # Calculate total score
        total_score = (r1_score + r2_score + sw1_score + sw2_score) / 4

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'r1_score': round(r1_score, 2),
            'r2_score': round(r2_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'r1_missing': r1_missing,
            'r2_missing': r2_missing,
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcb_status': 'correct' if pcb_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcb_correct) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 13"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcb_status": "ถูกต้อง" if pcb_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "r2_config": user_r2_config,
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "pca_config": {
                            "ip": pca_ip,
                            "subnet": pca_subnet
                        },
                        "pcb_config": {
                            "ip": pcb_ip,
                            "subnet": pcb_subnet
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))+ timedelta(hours=7)
                }},
                upsert=True
            )
            
            session['lab13_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab13.lab13'))

    result = session.get('lab13_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab13.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab13')