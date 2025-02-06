import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime 
from pymongo import MongoClient
from zoneinfo import ZoneInfo

lab9_bp = Blueprint('lab9', __name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab9_scores']

R1_KEYWORDS = [
   "hostname Branch1",
   "service password-encryption",
   {"interface Serial0/0/0": [
       "ip address 10.1.1.1 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap",
       "clock rate 128000"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.1.1 255.255.255.0"
   ]},
   "username Central password",
   {"router ospf 1": [
       "network 10.1.1.0 0.0.0.3 area 0",
       "network 192.168.1.0 0.0.0.255 area 0"
   ]}
]

R2_KEYWORDS = [
   "hostname Central",
   "service password-encryption",
   {"interface Serial0/0/0": [
       "ip address 10.1.1.2 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap"
   ]},
   {"interface Serial0/0/1": [
       "ip address 10.2.2.2 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap",
       "clock rate 128000"
   ]},
   {"interface Loopback0": [
       "ip address 209.165.200.225 255.255.255.224"
   ]},
   "username Branch3 password",
   "username Branch1 password",
   {"router ospf 1": [
       "network 10.1.1.0 0.0.0.3 area 0",
       "network 10.2.2.0 0.0.0.3 area 0",
       "default-information originate"
   ]},
   "ip route 0.0.0.0 0.0.0.0 Loopback0"
]

R3_KEYWORDS = [
   "hostname Branch3",
   "service password-encryption",
   {"interface Serial0/0/1": [
       "ip address 10.2.2.1 255.255.255.252", 
       "encapsulation ppp", 
       "ppp authentication chap"
   ]},
   {"interface GigabitEthernet0/1": [
       "ip address 192.168.3.1 255.255.255.0"
   ]},
   "username Central password",
   {"router ospf 1": [
       "network 10.2.2.0 0.0.0.3 area 0",
       "network 192.168.3.0 0.0.0.255 area 0"
   ]}
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

def check_pc_config(ip, subnet, gateway, correct_ip, correct_subnet, correct_gateway):
   return (
       ip == correct_ip and 
       subnet == correct_subnet and 
       gateway == correct_gateway
   )

@lab9_bp.route('/lab9')
def lab9():
   return render_template('lab9.html')

@lab9_bp.route('/check_config/lab9', methods=['POST'])
def check_config_lab9():
   user_r1_config = request.form.get('config_r1', '').strip()
   user_r2_config = request.form.get('config_r2', '').strip()
   user_r3_config = request.form.get('config_r3', '').strip()
   
   pca_ip = request.form.get('pc_a_ip', '').strip()
   pca_subnet = request.form.get('pc_a_subnet', '').strip() 
   pca_gateway = request.form.get('pc_a_gateway', '').strip()
   
   pcc_ip = request.form.get('pc_c_ip', '').strip()
   pcc_subnet = request.form.get('pc_c_subnet', '').strip()
   pcc_gateway = request.form.get('pc_c_gateway', '').strip()

   r1_score, r1_missing = check_keywords(user_r1_config, R1_KEYWORDS) 
   r2_score, r2_missing = check_keywords(user_r2_config, R2_KEYWORDS)
   r3_score, r3_missing = check_keywords(user_r3_config, R3_KEYWORDS)

   pca_correct = check_pc_config(pca_ip, pca_subnet, pca_gateway, "192.168.1.3", "255.255.255.0", "192.168.1.1")
   pcc_correct = check_pc_config(pcc_ip, pcc_subnet, pcc_gateway, "192.168.3.3", "255.255.255.0", "192.168.3.1")

   total_score = (r1_score + r2_score + r3_score) / 3

   bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

   scores_collection.insert_one({
       "username": session.get('username', 'unknown'),
       "lab": "Lab 9",
       "r1_score": r1_score,
       "r2_score": r2_score,
       "r3_score": r3_score,
       "pca_correct": "ถูกต้อง" if pca_correct else "ผิดพลาด",
       "pcc_correct": "ถูกต้อง" if pcc_correct else "ผิดพลาด", 
       "total_score": total_score,
       "timestamp": bangkok_time
   })

   result = f"""
   คะแนนรวม: {total_score:.2f}%<br>
   Branch1 (R1): คะแนน {r1_score:.2f}% ({'ถูกต้อง' if not r1_missing else f"ขาด: {', '.join(r1_missing)}"})<br>
   Central (R2): คะแนน {r2_score:.2f}% ({'ถูกต้อง' if not r2_missing else f"ขาด: {', '.join(r2_missing)}"})<br>
   Branch3 (R3): คะแนน {r3_score:.2f}% ({'ถูกต้อง' if not r3_missing else f"ขาด: {', '.join(r3_missing)}"})<br>
   PC A: {"ถูกต้อง" if pca_correct else "ผิดพลาด"}<br>
   PC C: {"ถูกต้อง" if pcc_correct else "ผิดพลาด"}<br>
   เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
   """

   return render_template('lab9.html', result=result)