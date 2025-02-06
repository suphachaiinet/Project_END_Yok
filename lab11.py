import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime 
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab11_bp = Blueprint('lab11', __name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab11_scores']

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

def check_keywords(user_config, keywords):
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

def check_vlan_config(vlan_config, expected_vlans):
   missing_vlans = []
   vlan_lines = vlan_config.splitlines()

   for vlan_id, vlan_name in expected_vlans.items():
       found = any(re.match(rf"^{vlan_id}\s+{vlan_name}", line) for line in vlan_lines)
       if not found:
           missing_vlans.append(f"VLAN {vlan_id}: {vlan_name} missing")

   return missing_vlans

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
   return (
       ip == correct_ip and 
       subnet == correct_subnet and 
       gateway == correct_gateway
   )

@lab11_bp.route('/lab11')
def lab11():
   return render_template('lab11.html')

@lab11_bp.route('/check_config/lab11', methods=['POST'])
def check_config_lab11():
   user_r1_config = request.form.get('config_r1', '').strip()
   user_r2_config = request.form.get('config_r2', '').strip()
   user_sw1_config = request.form.get('config_sw1', '').strip()
   user_sw2_config = request.form.get('config_sw2', '').strip()
   user_vlan_sw1 = request.form.get('vlan_sw1', '').strip()
   user_vlan_sw2 = request.form.get('vlan_sw2', '').strip()
   
   pca_ip = request.form.get('pc_a_ip', '').strip()
   pca_subnet = request.form.get('pc_a_subnet', '').strip() 
   pca_gateway = request.form.get('pc_a_gateway', '').strip()
   
   pcb_ip = request.form.get('pc_b_ip', '').strip()
   pcb_subnet = request.form.get('pc_b_subnet', '').strip()
   pcb_gateway = request.form.get('pc_b_gateway', '').strip()

   r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS) 
   r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
   sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
   sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

   vlan_sw1_missing = check_vlan_config(user_vlan_sw1, {
       "20": "Management", 
       "30": "Operations", 
       "40": "Sales",
       "999": "ParkingLot",
       "1000": "Native"
   })
   vlan_sw2_missing = check_vlan_config(user_vlan_sw2, {
       "20": "Management", 
       "30": "Operations", 
       "40": "Sales",
       "999": "ParkingLot",
       "1000": "Native"
   })

   pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "10.20.0.10", "255.255.255.0", "10.20.0.1")
   pcb_correct = check_pc_config(pcb_ip, pcb_subnet, pcb_gateway, "10.40.0.10", "255.255.255.0", "10.40.0.1")

   total_score = (r1_score + r2_score + sw1_score + sw2_score) / 4

   bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

   scores_collection.insert_one({
       "username": session.get('username', 'unknown'),
       "lab": "Lab 11",
       "r1_score": r1_score,
       "r2_score": r2_score,
       "sw1_score": sw1_score,
       "sw2_score": sw2_score,
       "pca_correct": "ถูกต้อง" if pca_correct else "ผิดพลาด",
       "pcb_correct": "ถูกต้อง" if pcb_correct else "ผิดพลาด", 
       "total_score": total_score,
       "timestamp": bangkok_time
   })

   result = f"""
   คะแนนรวม: {total_score:.2f}%<br>
   R1: คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
   R2: คะแนน {r2_score:.2f}% ({'ถูกต้อง' if not r2_missing else f"ขาด: {', '.join(r2_missing)}"})<br>
   S1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
   S2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
   VLAN S1: {"ถูกต้อง" if not vlan_sw1_missing else f"ขาด: {', '.join(vlan_sw1_missing)}"}<br>
   VLAN S2: {"ถูกต้อง" if not vlan_sw2_missing else f"ขาด: {', '.join(vlan_sw2_missing)}"}<br>
   PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
   PC B: {"ถูกต้อง" if pcb_correct else "ผิดพลาด"}<br>
   เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
   """

   return render_template('lab11.html', result=result)