import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab8_bp = Blueprint('lab8', __name__)

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
                        if re.match(r"^\s*(interface|!)\s*", l):
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
                re.search(rf"^\s*{re.escape(keyword)}\s*$", line) for line in user_lines
            )
            if keyword_found:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    score = (len(found_keywords) / total_keywords) * 100 if total_keywords > 0 else 0
    return score, missing_keywords

def check_vlan_config(vlan_config, expected_vlans):
    missing_vlans = []
    vlan_lines = vlan_config.splitlines()

    for vlan_id, vlan_name in expected_vlans.items():
        found = any(re.match(rf"^{vlan_id}\s+{vlan_name}", line) for line in vlan_lines)
        if not found:
            missing_vlans.append(f"VLAN {vlan_id}: {vlan_name}")

    return missing_vlans

def check_pc_config(ip, subnet, correct_ip, correct_subnet):
    return ip == correct_ip and subnet == correct_subnet

# Expected configurations
SW1_KEYWORDS = [
   "hostname S1",
   "service password-encryption",
   {"interface Port-channel1": ["switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/1": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/2": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
   {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]}
]

SW2_KEYWORDS = [
   "hostname S2",
   "service password-encryption",
   {"interface Port-channel1": ["switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/1": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/2": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
   {"interface FastEthernet0/18": ["switchport access vlan 20", "switchport mode access"]},
   {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]}
]

EXPECTED_VLANS = {
    "10": "Management",
    "20": "Sales",
    "1000": "Native"
}

EXPECTED_VLANS_SW2 = {
    "10": "Management",
    "20": "Clients",
    "1000": "Native"
}

@lab8_bp.route('/lab8', methods=['GET', 'POST'])
def lab8():
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
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw2_config = request.form.get('config_sw2', '').strip()
        user_vlan_sw1 = request.form.get('vlan_sw1', '').strip()
        user_vlan_sw2 = request.form.get('vlan_sw2', '').strip()
        
        pca_ip = request.form.get('pca_ip', '').strip()
        pca_subnet = request.form.get('pca_subnet', '').strip()
        
        pcb_ip = request.form.get('pcb_ip', '').strip()
        pcb_subnet = request.form.get('pcb_subnet', '').strip()

        # Check configurations
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        vlan_sw1_missing = check_vlan_config(user_vlan_sw1, EXPECTED_VLANS)
        vlan_sw2_missing = check_vlan_config(user_vlan_sw2, EXPECTED_VLANS_SW2)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, "192.168.20.3", "255.255.255.0")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, "192.168.20.4", "255.255.255.0")

        # Calculate total score
        total_score = (sw1_score * 0.5) + (sw2_score * 0.5)

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'vlan_sw1_missing': vlan_sw1_missing,
            'vlan_sw2_missing': vlan_sw2_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcb_status': 'correct' if pcb_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcb_correct and 
                                  not vlan_sw1_missing and not vlan_sw2_missing) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 8"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcb_status": "ถูกต้อง" if pcb_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "vlan_sw1": user_vlan_sw1,
                        "vlan_sw2": user_vlan_sw2,
                        "pca_config": {
                            "ip": pca_ip,
                            "subnet": pca_subnet
                        },
                        "pcb_config": {
                            "ip": pcb_ip,
                            "subnet": pcb_subnet
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
            session['lab8_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab8.lab8'))

    result = session.get('lab8_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab8.html', 
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                         active_lab='lab8')