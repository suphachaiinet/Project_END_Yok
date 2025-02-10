import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab14_bp = Blueprint('lab14', __name__)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab14_scores']

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

def check_keywords(user_config, keywords):
    """Check if configuration contains required keywords"""
    user_lines = user_config.splitlines()
    missing_keywords = []

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
                    break

            if not block_found:
                missing_keywords.append(f"{interface_name}: missing block")

        elif isinstance(keyword, str):
            keyword_found = any(
                re.search(rf"^\s*{re.escape(keyword)}\s*", line) for line in user_lines
            )
            if not keyword_found:
                missing_keywords.append(f"{keyword}: missing")

    score = (len(keywords) - len(missing_keywords)) / len(keywords) * 100
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

@lab14_bp.route('/lab14')
def lab14():
    return render_template('lab14.html')

@lab14_bp.route('/check_config/lab14', methods=['POST'])
def check_config_lab14():
    # Get configurations from form
    user_r1_config = request.form.get('config_r1', '').strip()
    user_r2_config = request.form.get('config_r2', '').strip()
    user_sw1_config = request.form.get('config_sw1', '').strip()
    user_sw2_config = request.form.get('config_sw2', '').strip()
    
    # Get PC configurations
    pca_ip = request.form.get('pc_a_ip', '').strip()
    pca_subnet = request.form.get('pc_a_subnet', '').strip()
    pca_gateway = request.form.get('pc_a_gateway', '').strip()
    
    pcb_ip = request.form.get('pc_b_ip', '').strip()
    pcb_subnet = request.form.get('pc_b_subnet', '').strip()
    pcb_gateway = request.form.get('pc_b_gateway', '').strip()

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

    # Get current time in Bangkok timezone
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # Save to MongoDB
    scores_collection.insert_one({
        "username": session.get('username', 'unknown'),
        "lab": "Lab 14",
        "r1_score": r1_score,
        "r2_score": r2_score,
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "pca_correct": "ถูกต้อง" if pca_correct else "ผิดพลาด",
        "pcb_correct": "ถูกต้อง" if pcb_correct else "ผิดพลาด",
        "total_score": total_score,
        "timestamp": bangkok_time
    })

    # Format result message
    result = f"""
    คะแนนรวม: {total_score:.2f}%<br>
    R1: คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
    R2: คะแนน {r2_score:.2f}% ({'ถูกต้อง' if not r2_missing else f"ขาด: {', '.join(r2_missing)}"})<br>
    S1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
    S2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
    PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
    PC B: {"ถูกต้อง" if pcb_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    return render_template('lab14.html', result=result)