import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime , timedelta
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab14_bp = Blueprint('lab14', __name__)

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

def check_pc_config(ip, subnet, gateway, correct_network):
    """Check if PC configuration is correct"""
    try:
        # Convert IP to binary for network comparison
        ip_parts = ip.split('.')
        if len(ip_parts) != 4:
            return False
        
        network_parts = correct_network.split('.')
        if len(network_parts) != 4:
            return False
            
        # Check if IP is in correct network
        for i in range(3):  # Check first three octets for network portion
            if ip_parts[i] != network_parts[i]:
                return False
                
        # Check if last octet is valid host ID
        last_octet = int(ip_parts[3])
        if last_octet < 2 or last_octet > 254:
            return False
            
        # Verify subnet mask
        if subnet != "255.255.255.0":
            return False
            
        # Verify default gateway
        if gateway != "192.168.1.1":
            return False
            
        return True
    except:
        return False

# Keywords for checking configurations
R1_KEYWORDS = [
    "hostname R1",
    "service password-encryption",
    "no ip domain-lookup",
    {"interface GigabitEthernet0/0/0": [
        "ip address 209.165.200.230 255.255.255.248",
        "duplex auto",
        "speed auto"
    ]},
    {"interface GigabitEthernet0/0/1": [
        "ip address 192.168.1.1 255.255.255.0",
        "duplex auto",
        "speed auto"
    ]},
    {"interface Loopback1": [
        "ip address 209.165.200.1 255.255.255.224"
    ]},
    "ip route 0.0.0.0 0.0.0.0 209.165.200.225",
    {"line con 0": [
        "password 7 0822455D0A16",
        "login"
    ]},
    {"line vty 0 4": [
        "password 7 0822455D0A16",
        "login"
    ]}
]

R2_KEYWORDS = [
    "hostname R2",
    "service password-encryption",
    "no ip domain-lookup",
    {"interface GigabitEthernet0/0/0": [
        "ip address 209.165.200.225 255.255.255.248",
        "duplex auto",
        "speed auto"
    ]},
    {"interface GigabitEthernet0/0/1": [
        "ip address 192.168.1.1 255.255.255.0",
        "duplex auto",
        "speed auto"
    ]},
    {"interface Loopback1": [
        "ip address 209.165.200.1 255.255.255.224"
    ]},
    "ip route 0.0.0.0 0.0.0.0 209.165.200.225",
    {"line con 0": [
        "password 7 0822455D0A16",
        "login"
    ]},
    {"line vty 0 4": [
        "password 7 0822455D0A16",
        "login"
    ]}
]

SW1_KEYWORDS = [
    "hostname S1",
    "service password-encryption",
    "no ip domain-lookup",
    "spanning-tree mode pvst",
    {"interface Vlan1": [
        "ip address 192.168.1.11 255.255.255.0"
    ]},
    "ip default-gateway 192.168.1.1",
    {"line con 0": [
        "password 7 0822455D0A16",
        "login"
    ]},
    {"line vty 0 4": [
        "password 7 0822455D0A16",
        "login"
    ]}
]

SW2_KEYWORDS = [
    "hostname S2",
    "service password-encryption", 
    "no ip domain-lookup",
    "spanning-tree mode pvst",
    {"interface Vlan1": [
        "ip address 192.168.1.12 255.255.255.0"
    ]},
    "ip default-gateway 192.168.1.1",
    {"line con 0": [
        "password 7 0822455D0A16",
        "login"
    ]},
    {"line vty 0 4": [
        "password 7 0822455D0A16",
        "login"
    ]}
]

@lab14_bp.route('/lab14', methods=['GET', 'POST'])
def lab14():
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
        user_sw1_config = request.form.get('config_sw1', '').strip()
        user_sw2_config = request.form.get('config_sw2', '').strip()
        
        # Get PC configurations
        pca_ip = request.form.get('pca_ip', '').strip()
        pca_subnet = request.form.get('pca_subnet', '').strip()
        pca_gateway = request.form.get('pca_gateway', '').strip()
        
        pcb_ip = request.form.get('pcb_ip', '').strip()
        pcb_subnet = request.form.get('pcb_subnet', '').strip()
        pcb_gateway = request.form.get('pcb_gateway', '').strip()

        # Check device configurations
        r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS)
        r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        # Check PC configurations
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.1.0")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway, "192.168.1.0")

        # Calculate total score (routers and switches are worth 80%, PCs are worth 20%)
        device_score = (r1_score + r2_score + sw1_score + sw2_score) / 4
        pc_score = ((1 if pca_correct else 0) + (1 if pcb_correct else 0)) * 50
        total_score = (device_score * 0.8) + (pc_score * 0.2)

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'device_score': round(device_score, 2),
            'pc_score': round(pc_score, 2),
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
            'status': 'success' if (device_score == 100 and pca_correct and pcb_correct) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 14"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "device_score": f"{device_score:.2f}/100",
                    "pc_score": f"{pc_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcb_status": "ถูกต้อง" if pcb_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "r1_config": user_r1_config,
                        "r2_config": user_r2_config,
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
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
            
            session['lab14_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab14.lab14'))

    result = session.get('lab14_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab14.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab14')