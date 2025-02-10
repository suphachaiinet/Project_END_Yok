import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab16_bp = Blueprint('lab16', __name__)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab16_scores']

# Keywords for checking configurations
R1_KEYWORDS = [
    "hostname R1",
    "no ip domain-lookup",
    {"interface Loopback0": [
        "ip address 10.10.1.1 255.255.255.0"
    ]},
    {"interface GigabitEthernet0/0/1": [
        "description Link to S1 Port 5",
        "ip address 192.168.10.1 255.255.255.0"
    ]},
    "ip dhcp excluded-address 192.168.10.1 192.168.10.9",
    "ip dhcp excluded-address 192.168.10.201 192.168.10.202",
    {"ip dhcp pool Students": [
        "network 192.168.10.0 255.255.255.0",
        "default-router 192.168.10.1",
        "domain-name CCNA2.Lab-11.6.1"
    ]}
]

SW1_KEYWORDS = [
    "hostname S1",
    "no ip domain-lookup",
    "spanning-tree mode pvst",
    {"vlan 10": ["name Management"]},
    {"vlan 333": ["name Native"]},
    {"vlan 999": ["name ParkingLot"]},
    {"interface FastEthernet0/1": [
        "description Link to S2",
        "switchport trunk encapsulation dot1q",
        "switchport trunk native vlan 333",
        "switchport mode trunk",
        "switchport nonegotiate"
    ]},
    {"interface FastEthernet0/5": [
        "description Link to R1",
        "switchport access vlan 10",
        "switchport mode access",
        "spanning-tree portfast"
    ]},
    {"interface FastEthernet0/6": [
        "description Link to PC-A",
        "switchport access vlan 10",
        "switchport mode access",
        "switchport port-security maximum 3",
        "switchport port-security violation restrict",
        "switchport port-security aging time 60",
        "switchport port-security aging type inactivity",
        "switchport port-security",
        "spanning-tree portfast",
        "spanning-tree bpduguard enable"
    ]},
    {"interface Vlan10": [
        "description Management SVI",
        "ip address 192.168.10.201 255.255.255.0"
    ]},
    "ip default-gateway 192.168.10.1"
]

SW2_KEYWORDS = [
    "hostname S2",
    "no ip domain-lookup",
    "ip dhcp snooping vlan 10",
    "ip dhcp snooping",
    "spanning-tree mode pvst",
    {"vlan 10": ["name Students"]},
    {"vlan 333": ["name Native"]},
    {"vlan 999": ["name ParkingLot"]},
    {"interface FastEthernet0/1": [
        "description Link to S1",
        "switchport trunk native vlan 333",
        "switchport mode trunk",
        "switchport nonegotiate",
        "ip dhcp snooping trust"
    ]},
    {"interface FastEthernet0/18": [
        "description Link to PC-B",
        "switchport access vlan 10",
        "switchport mode access",
        "switchport port-security maximum 2",
        "switchport port-security violation protect",
        "switchport port-security mac-address sticky",
        "switchport port-security aging time 60",
        "switchport port-security",
        "spanning-tree portfast",
        "spanning-tree bpduguard enable",
        "ip dhcp snooping limit rate 5"
    ]},
    {"interface Vlan10": [
        "description Management SVI",
        "ip address 192.168.10.202 255.255.255.0"
    ]},
    "ip default-gateway 192.168.10.1"
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
                        if re.match(r"^\s*(interface|!|router|vlan)\s*", l):
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

@lab16_bp.route('/lab16')
def lab16():
    """Display lab16.html"""
    return render_template('lab16.html')

@lab16_bp.route('/check_config/lab16', methods=['POST'])
def check_config_lab16():
    """Check configurations and return results"""
    # Get configurations from form
    user_r1_config = request.form.get('config_r1', '').strip()
    user_sw1_config = request.form.get('config_sw1', '').strip()
    user_sw2_config = request.form.get('config_sw2', '').strip()
    
    # Check device configurations
    r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS)
    sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
    sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

    # Calculate total score
    # Router: 30%, Switch1: 35%, Switch2: 35%
    total_score = (r1_score * 0.3) + (sw1_score * 0.35) + (sw2_score * 0.35)

    # Get current time in Bangkok timezone
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # Save to MongoDB
    scores_collection.insert_one({
        "username": session.get('username', 'unknown'),
        "lab": "Lab 16",
        "r1_score": r1_score,
        "sw1_score": sw1_score,
        "sw2_score": sw2_score,
        "total_score": total_score,
        "timestamp": bangkok_time
    })

    # Format result message
    result = f"""
    คะแนนรวม: {total_score:.2f}%<br>
    Router Configuration:
    - R1: คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
    Switch Configurations:
    - S1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
    - S2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    return render_template('lab16.html', result=result)