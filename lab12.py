import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime , timedelta
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab12_bp = Blueprint('lab12', __name__)

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
                        if re.match(r"^\s*(interface|!|ip dhcp|router)\s*", l):
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

def check_dhcp_pool(user_config):
    # ตรวจสอบการกำหนด DHCP Pool
    dhcp_pools = {
        "R1_Client_LAN": {
            "network": "192.168.1.0 255.255.255.192",
            "excluded_addresses": [
                "192.168.1.1 192.168.1.5"
            ],
            "default_router": "192.168.1.1",
            "domain_name": "ccna-lab.com",
            "lease_time": "2 12 30"
        },
        "R2_Client_LAN": {
            "network": "192.168.1.96 255.255.255.240",
            "excluded_addresses": [
                "192.168.1.97 192.168.1.101"
            ],
            "default_router": "192.168.1.97",
            "domain_name": "ccna-lab.com",
            "lease_time": "2 12 30"
        }
    }

    missing_dhcp_configs = []
    
    for pool_name, pool_details in dhcp_pools.items():
        # ตรวจสอบ Network
        network_found = any(
            pool_details["network"] in line 
            for line in user_config.splitlines()
        )
        if not network_found:
            missing_dhcp_configs.append(f"DHCP Pool {pool_name}: Network missing")
        
        # ตรวจสอบ Excluded Addresses
        for excluded_range in pool_details["excluded_addresses"]:
            excluded_found = any(
                excluded_range in line 
                for line in user_config.splitlines()
            )
            if not excluded_found:
                missing_dhcp_configs.append(f"DHCP Pool {pool_name}: Excluded Address {excluded_range} missing")
        
        # ตรวจสอบ Default Router
        router_found = any(
            f"default-router {pool_details['default_router']}" in line 
            for line in user_config.splitlines()
        )
        if not router_found:
            missing_dhcp_configs.append(f"DHCP Pool {pool_name}: Default Router missing")
        
        # ตรวจสอบ Domain Name
        domain_found = any(
            f"domain-name {pool_details['domain_name']}" in line 
            for line in user_config.splitlines()
        )
        if not domain_found:
            missing_dhcp_configs.append(f"DHCP Pool {pool_name}: Domain Name missing")
        
        # ตรวจสอบ Lease Time
        lease_found = any(
            f"lease {pool_details['lease_time']}" in line 
            for line in user_config.splitlines()
        )
        if not lease_found:
            missing_dhcp_configs.append(f"DHCP Pool {pool_name}: Lease Time missing")
    
    return missing_dhcp_configs

# Expected configurations
R1_KEYWORDS = [
   "hostname R1",
   "service password-encryption",
   {"interface GigabitEthernet0/0/0": [
       "ip address 10.0.0.1 255.255.255.252"
   ]},
   {"interface GigabitEthernet0/0/1.100": [
       "description Connected to Client Network",
       "encapsulation dot1Q 100",
       "ip address 192.168.1.1 255.255.255.192"
   ]},
   {"interface GigabitEthernet0/0/1.200": [
       "description Connected to Management Network", 
       "encapsulation dot1Q 200",
       "ip address 192.168.1.65 255.255.255.224"
   ]},
   "ip dhcp excluded-address 192.168.1.1 192.168.1.5",
   "ip dhcp excluded-address 192.168.1.97 192.168.1.101",
   {"ip dhcp pool R1_Client_LAN": [
       "network 192.168.1.0 255.255.255.192",
       "domain-name ccna-lab.com",
       "default-router 192.168.1.1",
       "lease 2 12 30"
   ]},
   {"ip dhcp pool R2_Client_LAN": [
       "network 192.168.1.96 255.255.255.240",
       "default-router 192.168.1.97", 
       "domain-name ccna-lab.com",
       "lease 2 12 30"
   ]}
]

R2_KEYWORDS = [
   "hostname R2",
   "service password-encryption",
   {"interface GigabitEthernet0/0/0": [
       "ip address 10.0.0.2 255.255.255.252"
   ]},
   {"interface GigabitEthernet0/0/1": [
       "ip address 192.168.1.97 255.255.255.240",
       "ip helper-address 10.0.0.1"
   ]}
]

SW1_KEYWORDS = [
   "hostname S1",
   "service password-encryption",
   {"interface Vlan200": [
       "ip address 192.168.1.66 255.255.255.224"
   ]},
   "ip default-gateway 192.168.1.65",
   {"interface FastEthernet0/5": [
       "switchport trunk allowed vlan 100,200,1000",
       "switchport trunk native vlan 1000",
       "switchport mode trunk"
   ]},
   {"interface FastEthernet0/6": [
       "switchport access vlan 100",
       "switchport mode access"
   ]}
]

SW2_KEYWORDS = [
   "hostname S2",
   "service password-encryption",
   {"interface Vlan1": [
       "ip address 192.168.1.98 255.255.255.240"
   ]},
   "ip default-gateway 192.168.1.97"
]

EXPECTED_VLANS = {
    "1": "default", 
    "100": "Clients", 
    "200": "Management", 
    "999": "Parking_Lot",
    "1000": "Native"
}

@lab12_bp.route('/lab12', methods=['GET', 'POST'])
def lab12():
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
        pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.1.3", "255.255.255.192", "192.168.1.1")
        pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway, "192.168.1.100", "255.255.255.240", "192.168.1.97")

        # ตรวจสอบ DHCP Pool
        dhcp_pool_missing = check_dhcp_pool(user_r1_config)

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
            'dhcp_pool_missing': dhcp_pool_missing,
            'pca_status': 'correct' if pca_correct else 'incorrect',
            'pcb_status': 'correct' if pcb_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pca_correct and pcb_correct and 
                                  not vlan_sw1_missing and not vlan_sw2_missing and
                                  not dhcp_pool_missing) else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 12"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "r1_score": f"{r1_score:.2f}/100",
                    "r2_score": f"{r2_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pca_status": "ถูกต้อง" if pca_correct else "ไม่ถูกต้อง",
                    "pcb_status": "ถูกต้อง" if pcb_correct else "ไม่ถูกต้อง",
                    "dhcp_pool_missing": dhcp_pool_missing,
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
            
            session['lab12_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab12.lab12'))

    result = session.get('lab12_result')

    # Debug print
    print(f"Username: {username}")
    print(f"User Info: {user}")
    print(f"First Name: {first_name}")
    print(f"Last Name: {last_name}")

    return render_template('lab12.html', 
                        result=result,
                        scores=lab_scores,
                        overall_score=overall_score,
                        first_name=first_name,
                        last_name=last_name,
                        active_lab='lab12')