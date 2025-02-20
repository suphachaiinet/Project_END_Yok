import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab9_bp = Blueprint('lab9', __name__)

# MongoDB Connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']

def check_keywords(user_config, keywords):
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
                        if re.match(r"^\s*(interface|!|router)\s*", l):
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

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
    return (
        ip == correct_ip and 
        subnet == correct_subnet and 
        gateway == correct_gateway
    )

# Expected configurations
R1_KEYWORDS = [
   "hostname Branch1",
   "service password-encryption",
   {"interface Serial0/0/0": [
       "ip address 10.1.1.1 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap",
       "clock rate 128000"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.1.1 255.255.255.0"
   ]},
   "username Central password",
   {"router ospf 1": [
       "network 10.1.1.0 0.0.0.3 area 0",
       "network 192.168.1.0 0.0.0.255 area 0"
   ]}
]

R2_KEYWORDS = [
   "hostname Central",
   "service password-encryption",
   {"interface Serial0/0/0": [
       "ip address 10.1.1.2 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap"
   ]},
   {"interface Serial0/0/1": [
       "ip address 10.2.2.2 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap",
       "clock rate 128000"
   ]},
   {"interface Loopback0": [
       "ip address 209.165.200.225 255.255.255.224"
   ]},
   "username Branch3 password",
   "username Branch1 password",
   {"router ospf 1": [
       "network 10.1.1.0 0.0.0.3 area 0",
       "network 10.2.2.0 0.0.0.3 area 0",
       "default-information originate"
   ]},
   "ip route 0.0.0.0 0.0.0.0 Loopback0"
]

R3_KEYWORDS = [
   "hostname Branch3",
   "service password-encryption",
   {"interface Serial0/0/1": [
       "ip address 10.2.2.1 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.3.1 255.255.255.0"
   ]},
   "username Central password",
   {"router ospf 1": [
       "network 10.2.2.0 0.0.0.3 area 0",
       "network 192.168.3.0 0.0.0.255 area 0"
   ]}
]

@lab9_bp.route('/lab9', methods=['GET', 'POST'])
def lab9():
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
        user_r3_config = request.form.get('config_r3', '').strip()
        
        pca_ip = request.form.get('pca_ip', '').strip()
        pca_subnet = request.form.get('pca_subnet', '').strip() 
        pca_gateway = request.form.get('pca_gateway', '').strip()
        
        pcc_ip = request.form.get('pcc_ip', '').strip()
        pcc_subnet = request.form.get('pcc_subnet', '').strip()
        pcc_gateway = request.form.get('pcc_gateway', '').strip()

        # Check configurations
        r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS) 
        r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
        r3_score, r3_missing = check_keywords(user_r3_config, R3_KEYWORDS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.1.3", "255.255.255.0", "192.168.1.1")
        pcc_correct = check_pc_config(pcc_ip, pcc_subnet, pcc_gateway, "192.168.3.3", "255.255.255.0", "192.168.3.1")

        # Calculate total score
        total_score = (r1_score + r2_score + r3_score) / 3

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'r1_score': round(r1_score, 2),
            'r2_score': round(r2_score, 2),
            'r3_score': round(r3_score, 2),
            'r1_missing': r1_missing,
            'r2_missing': r2_missing,
            'r3_missing': r3_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcc_status': 'correct' if pcc_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcc_correct) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 9"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "r3_score": f"{r3_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcc_status": "ถูกต้อง" if pcc_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "r2_config": user_r2_config,
                        "r3_config": user_r3_config,
                        "pca_config": {
                            "ip": pca_ip,
                            "subnet": pca_subnet,
                            "gateway": pca_gateway
                        },
                        "pcc_config": {
                            "ip": pcc_ip,
                            "subnet": pcc_subnet,
                            "gateway": pcc_gateway
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
            session['lab9_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab9.lab9'))

    result = session.get('lab9_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab9.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab9')