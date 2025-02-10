import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab15_bp = Blueprint('lab15', __name__)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab15_scores']

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

def check_pc_config(ip, subnet, gateway):
    """Verify PC configuration"""
    try:
        # Check IP format and range
        ip_parts = [int(p) for p in ip.split('.')]
        if len(ip_parts) != 4 or not all(0 <= p <= 255 for p in ip_parts):
            return False
            
        # Check if IP is in correct network (192.168.1.0/24)
        if ip_parts[0] != 192 or ip_parts[1] != 168 or ip_parts[2] != 1:
            return False
            
        # Check if host portion is valid (not 0, 255, or used by other devices)
        if ip_parts[3] in [0, 255, 1, 3, 11, 13, 254]:
            return False
            
        # Verify subnet mask
        if subnet != "255.255.255.0":
            return False
            
        # Verify gateway (virtual IP from HSRP)
        if gateway != "192.168.1.254":
            return False
            
        return True
    except:
        return False

@lab15_bp.route('/lab15')
def lab15():
    """Display lab15.html"""
    return render_template('lab15.html')

@lab15_bp.route('/check_config/lab15', methods=['POST'])
def check_config_lab15():
    """Check configurations and return results"""
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

    # Check PC configurations
    pc_a_correct = check_pc_config(pc_a_ip, pc_a_subnet, pc_a_gateway)
    pc_c_correct = check_pc_config(pc_c_ip, pc_c_subnet, pc_c_gateway)

    # Calculate total score 
    # Routers: 45% (15% each)
    # Switches: 25% (12.5% each)
    # PCs: 30% (15% each)
    router_score = (r1_score + r2_score + r3_score) / 3 * 0.45
    switch_score = (sw1_score + sw2_score) / 2 * 0.25
    pc_score = ((1 if pc_a_correct else 0) + (1 if pc_c_correct else 0)) * 15
    total_score = router_score + switch_score + pc_score

    # Get current time in Bangkok timezone
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # Save to MongoDB
    scores_collection.insert_one({
        "username": session.get('username', 'unknown'),
        "lab": "Lab 15",
        "r1_score": r1_score,
        "r2_score": r2_score,
        "r3_score": r3_score,
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "pc_a_correct": "ถูกต้อง" if pc_a_correct else "ผิดพลาด",
        "pc_c_correct": "ถูกต้อง" if pc_c_correct else "ผิดพลาด",
        "total_score": total_score,
        "timestamp": bangkok_time
    })

    # Format result message
    result = f"""
    คะแนนรวม: {total_score:.2f}%<br>
    Router Configurations:
    - R1: คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
    - R2: คะแนน {r2_score:.2f}% ({'ถูกต้อง' if not r2_missing else f"ขาด: {', '.join(r2_missing)}"})<br>
    - R3: คะแนน {r3_score:.2f}% ({'ถูกต้อง' if not r3_missing else f"ขาด: {', '.join(r3_missing)}"})<br>
    Switch Configurations:
    - S1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
    - S3: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
    PC Configurations:
    - PC-A: {"ถูกต้อง" if pc_a_correct else "ผิดพลาด"}<br>
    - PC-C: {"ถูกต้อง" if pc_c_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    return render_template('lab15.html', result=result)