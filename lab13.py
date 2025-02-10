import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime 
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab13_bp = Blueprint('lab13', __name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab13_scores']

R1_KEYWORDS = [
   "hostname R1",
   "service password-encryption",
   "ipv6 unicast-routing",
   {"ipv6 dhcp pool R1-STATELESS": [
       "dns-server 2001:DB8:ACAD::254",
       "domain-name STATELESS.com"
   ]},
   {"ipv6 dhcp pool R2-STATEFUL": [
       "address prefix 2001:DB8:ACAD:3:AAAA::/80",
       "dns-server 2001:DB8:ACAD::254",
       "domain-name STATEFUL.com"
   ]},
   {"interface GigabitEthernet0/0/0": [
       "ipv6 address 2001:DB8:ACAD:2::1/64",
       "ipv6 address FE80::1 link-local",
       "ipv6 dhcp server R2-STATEFUL"
   ]},
   {"interface GigabitEthernet0/0/1": [
       "ipv6 address 2001:DB8:ACAD:1::1/64",
       "ipv6 address FE80::1 link-local",
       "ipv6 nd other-config-flag",
       "ipv6 dhcp server R1-STATELESS"
   ]},
   "ipv6 route ::/0 2001:DB8:ACAD:2::2"
]

R2_KEYWORDS = [
   "hostname R2",
   "service password-encryption",
   "ipv6 unicast-routing",
   {"interface GigabitEthernet0/0/0": [
       "ipv6 address 2001:DB8:ACAD:2::2/64",
       "ipv6 address FE80::2 link-local"
   ]},
   {"interface GigabitEthernet0/0/1": [
       "ipv6 address 2001:DB8:ACAD:3::1/64",
       "ipv6 address FE80::2 link-local",
       "ipv6 nd prefix 2001:DB8:ACAD:3::/64 2592000 604800 no-autoconfig",
       "ipv6 nd managed-config-flag",
       "ipv6 dhcp relay destination 2001:DB8:ACAD:2::1 GigabitEthernet0/0/0"
   ]},
   "ipv6 route ::/0 2001:DB8:ACAD:2::1"
]

SW1_KEYWORDS = [
   "hostname S1",
   "service password-encryption",
   "spanning-tree mode pvst"
]

SW2_KEYWORDS = [
   "hostname S2",
   "service password-encryption", 
   "spanning-tree mode pvst"
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

def check_pc_config(ip, subnet, correct_ip_prefix):
   return ip.startswith(correct_ip_prefix)

@lab13_bp.route('/lab13')
def lab13():
   return render_template('lab13.html')

@lab13_bp.route('/check_config/lab13', methods=['POST'])
def check_config_lab13():
   user_r1_config = request.form.get('config_r1', '').strip()
   user_r2_config = request.form.get('config_r2', '').strip()
   user_sw1_config = request.form.get('config_sw1', '').strip()
   user_sw2_config = request.form.get('config_sw2', '').strip()
   
   pca_ip = request.form.get('pc_a_ip', '').strip()
   pca_subnet = request.form.get('pc_a_subnet', '').strip() 
   
   pcb_ip = request.form.get('pc_b_ip', '').strip()
   pcb_subnet = request.form.get('pc_b_subnet', '').strip()

   r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS) 
   r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
   sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
   sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

   pca_correct = check_pc_config(pca_ip, pca_subnet, "2001:db8:acad:1:")
   pcb_correct = check_pc_config(pcb_ip, pcb_subnet, "2001:db8:acad:3:")

   total_score = (r1_score + r2_score + sw1_score + sw2_score) / 4

   bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

   scores_collection.insert_one({
       "username": session.get('username', 'unknown'),
       "lab": "Lab 13",
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
   PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
   PC B: {"ถูกต้อง" if pcb_correct else "ผิดพลาด"}<br>
   เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
   """

   return render_template('lab13.html', result=result)