import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab10_bp = Blueprint('lab10', __name__)

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
                        if re.match(r"^\s*(interface|!|router|ip access-list)\s*", l):
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
   "hostname R1",
   "no service password-encryption",
   {"interface Loopback0": [
       "ip address 192.168.20.1 255.255.255.0"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.10.1 255.255.255.0",
       "ip access-group BRANCH-OFFICE-POLICY out"
   ]},
   {"interface Serial0/0/0": [
       "ip address 10.1.1.1 255.255.255.252",
       "clock rate 128000"
   ]},
   {"router rip": [
       "version 2",
       "network 10.1.1.0",
       "network 192.168.10.0",
       "network 192.168.20.0"
   ]},
   {"ip access-list standard BRANCH-OFFICE-POLICY": [
       "permit 192.168.30.3",
       "permit 192.168.40.0 0.0.0.255",
       "permit 209.165.200.224 0.0.0.31",
       "deny any"
   ]}
]

R2_KEYWORDS = [
   "hostname ISP",
   "no service password-encrypt",
   {"interface Loopback0": [
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
       "version 2",
       "network 10.1.1.0",
       "network 10.2.2.0",
       "network 209.165.200.224"
   ]}
]

R3_KEYWORDS = [
   "hostname R3",
   "no service password-encryption",
   {"interface Loopback0": [
       "ip address 192.168.40.1 255.255.255.0"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.30.1 255.255.255.0",
       "ip access-group 1 out"
   ]},
   {"interface Serial0/0/1": [
       "ip address 10.2.2.1 255.255.255.252"
   ]},
   {"router rip": [
       "version 2",
       "network 10.2.2.0",
       "network 192.168.30.0",
       "network 192.168.40.0"
   ]},
   "access-list 1 remark Allow R1 LANs Access",
    "access-list 1 permit 192.168.10.0 0.0.0.255",
    "access-list 1 permit 192.168.20.0 0.0.0.255",
    "access-list 1 deny any"
]

SW1_KEYWORDS = [
   "hostname S1",
   "no service password-encryption",
   {"interface Vlan1": [
       "ip address 192.168.10.11 255.255.255.0"
   ]},
   "ip default-gateway 192.168.10.1"
]

SW3_KEYWORDS = [
   "hostname S3",
   "no service password-encryption",
   {"interface Vlan1": [
       "ip address 192.168.30.11 255.255.255.0"
   ]},
   "ip default-gateway 192.168.30.1"
]

@lab10_bp.route('/lab10', methods=['GET', 'POST'])
def lab10():
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
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw3_config = request.form.get('config_sw3', '').strip()
        
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
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw3_score, sw3_missing = check_keywords(user_sw3_config, SW3_KEYWORDS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.10.3", "255.255.255.0", "192.168.10.1")
        pcc_correct = check_pc_config(pcc_ip, pcc_subnet, pcc_gateway, "192.168.30.3", "255.255.255.0", "192.168.30.1")

        # Calculate total score
        total_score = (r1_score + r2_score + r3_score + sw1_score + sw3_score) / 5

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'r1_score': round(r1_score, 2),
            'r2_score': round(r2_score, 2),
            'r3_score': round(r3_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw3_score': round(sw3_score, 2),
            'r1_missing': r1_missing,
            'r2_missing': r2_missing,
            'r3_missing': r3_missing,
            'sw1_missing': sw1_missing,
            'sw3_missing': sw3_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcc_status': 'correct' if pcc_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcc_correct) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 10"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "r3_score": f"{r3_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw3_score": f"{sw3_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcc_status": "ถูกต้อง" if pcc_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "r2_config": user_r2_config,
                        "r3_config": user_r3_config,
                        "sw1_config": user_sw1_config,
                        "sw3_config": user_sw3_config,
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
            
            session['lab10_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab10.lab10'))

    result = session.get('lab10_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab10.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab10')