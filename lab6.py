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

lab6_bp = Blueprint('lab6', __name__)

# แก้ไขในส่วน MongoDB Connection ของ lab.py
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']
users_collection = db['users_all']  # เพิ่มบรรทัดนี้ให้ชัดเจน

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

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
    return ip == correct_ip and subnet == correct_subnet and gateway == correct_gateway

# Expected configurations
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

EXPECTED_VLANS = {
    "3": "Management",
    "4": "Operations",
    "8": "Native"
}

@lab6_bp.route('/lab6', methods=['GET', 'POST'])
def lab6():
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

        # Check configurations
        r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS)
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        vlan_sw1_missing = check_vlan_config(user_vlan_sw1, EXPECTED_VLANS)
        vlan_sw2_missing = check_vlan_config(user_vlan_sw2, EXPECTED_VLANS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, 
                                    "192.168.3.3", "255.255.255.0", "192.168.3.1")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway,
                                    "192.168.4.3", "255.255.255.0", "192.168.4.1")

        # Calculate total score
        total_score = (r1_score * 0.3) + (sw1_score * 0.35) + (sw2_score * 0.35)

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'r1_score': round(r1_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'r1_missing': r1_missing,
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
                {"username": username, "lab": "Lab 6"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcb_status": "ถูกต้อง" if pcb_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "vlan_sw1": user_vlan_sw1,
                        "vlan_sw2": user_vlan_sw2,
                        "pca_config": {
                            "ip": pca_ip,
                            "subnet": pca_subnet,
                            "gateway": pca_gateway
                        },
                        "pcb_config": {
                            "ip": pcb_ip,
                            "subnet": pcb_subnet,
                            "gateway": pcb_gateway
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))+ timedelta(hours=7)
                }},
                upsert=True
            )
            
            session['lab6_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab6.lab6'))

    # สำหรับ GET request
    result = session.get('lab6_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab6.html', 
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                            active_lab='lab6'
                            )
                     