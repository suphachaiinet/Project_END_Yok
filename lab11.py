import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime , timedelta
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab11_bp = Blueprint('lab11', __name__)

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

def check_vlan_config(vlan_config, expected_vlans):
    missing_vlans = []
    vlan_lines = vlan_config.splitlines()

    for vlan_id, vlan_name in expected_vlans.items():
        found = any(re.match(rf"^{vlan_id}\s+{vlan_name}", line) for line in vlan_lines)
        if not found:
            missing_vlans.append(f"VLAN {vlan_id}: {vlan_name}")

    return missing_vlans

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
    return (
        ip == correct_ip and 
        subnet == correct_subnet and 
        gateway == correct_gateway
    )

# Expected configurations
R1_KEYWORDS = [
   "hostname R1",
   "service password-encryption",
   {"interface Loopback1": [
       "ip address 172.16.1.1 255.255.255.0"
   ]},
   {"interface GigabitEthernet0/0/1.20": [
       "description Management Network",
       "encapsulation dot1Q 20",
       "ip address 10.20.0.1 255.255.255.0"
   ]},
   {"interface GigabitEthernet0/0/1.30": [
       "description Operations Network",
       "encapsulation dot1Q 30",
       "ip address 10.30.0.1 255.255.255.0",
       "ip access-group 102 in"
   ]},
   {"interface GigabitEthernet0/0/1.40": [
       "description Sales Network",
       "encapsulation dot1Q 40",
       "ip address 10.40.0.1 255.255.255.0",
       "ip access-group 101 in"
   ]},
   "access-list 101 remark ACL 101 fulfills policies 1, 2, and 3",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq 22",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq www",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.30.0.1 eq www",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.40.0.1 eq www",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq 443",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.30.0.1 eq 443",
    "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.40.0.1 eq 443",
    "access-list 101 deny icmp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 echo",
    "access-list 101 deny icmp 10.40.0.0 0.0.0.255 10.30.0.0 0.0.0.255 echo",
    "access-list 101 permit ip any any",
    "access-list 102 remark ACL 102 fulfills policy 4",
    "access-list 102 deny icmp 10.30.0.0 0.0.0.255 10.40.0.0 0.0.0.255 echo",
    "access-list 102 permit ip any any",
]

R2_KEYWORDS = [
   "hostname R2",
   "service password-encryption",
   {"interface GigabitEthernet0/0/1": [
       "ip address 10.20.0.4 255.255.255.0"
   ]},
   "ip route 0.0.0.0 0.0.0.0 10.20.0.1"
]

SW1_KEYWORDS = [
   "hostname S1",
   "service password-encryption",
   {"interface Vlan20": [
       "ip address 10.20.0.2 255.255.255.0"
   ]},
   "ip default-gateway 10.20.0.1"
]

SW2_KEYWORDS = [
   "hostname S2",
   "service password-encryption",
   {"interface Vlan20": [
       "ip address 10.20.0.3 255.255.255.0"
   ]},
   {"interface FastEthernet0/1": [
       "switchport trunk allowed vlan 20,30,40,1000",
       "switchport trunk native vlan 1000",
       "switchport mode trunk"
   ]},
   {"interface FastEthernet0/5": [
       "switchport access vlan 20",
       "switchport mode access"
   ]},
   {"interface FastEthernet0/18": [
       "switchport access vlan 40",
       "switchport mode access"
   ]},
   "ip default-gateway 10.20.0.1"
]

EXPECTED_VLANS = {
    "20": "Management", 
    "30": "Operations", 
    "40": "Sales",
    "999": "ParkingLot",
    "1000": "Native"
}

@lab11_bp.route('/lab11', methods=['GET', 'POST'])
def lab11():
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
        r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        vlan_sw1_missing = check_vlan_config(user_vlan_sw1, EXPECTED_VLANS)
        vlan_sw2_missing = check_vlan_config(user_vlan_sw2, EXPECTED_VLANS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "10.30.0.10", "255.255.255.0", "10.30.0.1")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway, "10.40.0.10", "255.255.255.0", "10.40.0.1")

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
            'vlan_sw1_missing': vlan_sw1_missing,
            'vlan_sw2_missing': vlan_sw2_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcb_status': 'correct' if pcb_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcb_correct and 
                                  not vlan_sw1_missing and not vlan_sw2_missing) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 11"},
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
            
            session['lab11_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab11.lab11'))

    result = session.get('lab11_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab11.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab11')