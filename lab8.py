import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime 
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab8_bp = Blueprint('lab8', __name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab8_scores']

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
               re.search(rf"^\s*{re.escape(keyword)}\s*$", line) for line in user_lines
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

def check_pc_config(ip, subnet, correct_ip, correct_subnet):
   return ip == correct_ip and subnet == correct_subnet

@lab8_bp.route('/lab8')
def lab8():
   return render_template('lab8.html')

@lab8_bp.route('/check_config/lab8', methods=['POST'])
def check_config_lab8():
   user_sw1_config = request.form.get('config_sw1', '').strip()
   user_sw2_config = request.form.get('config_sw2', '').strip()
   user_vlan_sw1 = request.form.get('vlan_sw1', '').strip()
   user_vlan_sw2 = request.form.get('vlan_sw2', '').strip()
   
   pca_ip = request.form.get('pc_a_ip', '').strip()
   pca_subnet = request.form.get('pc_a_subnet', '').strip() 
   
   pcb_ip = request.form.get('pc_b_ip', '').strip()
   pcb_subnet = request.form.get('pc_b_subnet', '').strip()

   sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS) 
   sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

   vlan_sw1_missing = check_vlan_config(user_vlan_sw1, {"10": "Management", "20": "Sales", "1000": "Native"})
   vlan_sw2_missing = check_vlan_config(user_vlan_sw2, {"10": "Management", "20": "Clients", "1000": "Native"})

   pca_correct = check_pc_config(pca_ip, pca_subnet, "192.168.20.3", "255.255.255.0")
   pcb_correct = check_pc_config(pcb_ip, pcb_subnet, "192.168.20.4", "255.255.255.0")

   total_score = (sw1_score + sw2_score) / 2

   bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

   scores_collection.insert_one({
       "username": session.get('username', 'unknown'),
       "lab": "Lab 8",
       "sw1_score": sw1_score,
       "sw2_score": sw2_score,
       "vlan_sw1_missing": vlan_sw1_missing,
       "vlan_sw2_missing": vlan_sw2_missing,
       "pca_correct": "ถูกต้อง" if pca_correct else "ผิดพลาด",
       "pcb_correct": "ถูกต้อง" if pcb_correct else "ผิดพลาด", 
       "total_score": total_score,
       "timestamp": bangkok_time
   })

   result = f"""
   คะแนนรวม: {total_score:.2f}%<br>
   SW1: คะแนน {sw1_score:.2f}% ({'ถูกต้อง' if not sw1_missing else f"ขาด: {', '.join(sw1_missing)}"})<br>
   SW2: คะแนน {sw2_score:.2f}% ({'ถูกต้อง' if not sw2_missing else f"ขาด: {', '.join(sw2_missing)}"})<br>
   VLAN SW1: {"ถูกต้อง" if not vlan_sw1_missing else f"ขาด: {', '.join(vlan_sw1_missing)}"}<br>
   VLAN SW2: {"ถูกต้อง" if not vlan_sw2_missing else f"ขาด: {', '.join(vlan_sw2_missing)}"}<br>
   PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
   PC B: {"ถูกต้อง" if pcb_correct else "ผิดพลาด"}<br>
   เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
   """

   return render_template('lab8.html', result=result)