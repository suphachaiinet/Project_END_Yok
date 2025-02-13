import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab_bp = Blueprint('lab', __name__)

def parse_interfaces(config_text):
    interfaces = {}
    current_interface = None
    lines = config_text.splitlines()

    for line in lines:
        line = line.strip()
        if line.startswith("interface"):
            current_interface = line
            interfaces[current_interface] = []
        elif current_interface and line:
            interfaces[current_interface].append(line)
    return interfaces

def check_interface_block(interface_block, expected_commands):
    missing_commands = [cmd for cmd in expected_commands if cmd not in interface_block]
    return missing_commands

def check_keywords(user_config, keywords):
    user_interfaces = parse_interfaces(user_config)
    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]

            if interface_name in user_interfaces:
                missing = check_interface_block(user_interfaces[interface_name], expected_commands)
                if not missing:
                    found_keywords.append(interface_name)
                else:
                    missing_keywords.extend([f"{interface_name}: {cmd}" for cmd in missing])
            else:
                missing_keywords.append(f"{interface_name}: (missing block)")
        else:
            if any(keyword in line for line in user_config.lower().splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords

KEYWORDS = [
    "service password-encryption",
    "hostname s1",
    "no ip domain-lookup",
    {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
    {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0", "ip default-gateway 192.168.1.1"]}
]

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab_scores']

@lab_bp.route('/lab1')
def lab1():
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1', methods=['POST'])
def check_config_lab1():
   username = session.get('username', 'unknown')
   user_switch_config = request.form.get('config_switch', '').strip()

   # PC Config
   user_pc_ip = request.form.get('pc_ip_address', '').strip()
   user_pc_subnet = request.form.get('pc_subnet_mask', '').strip()
   user_pc_gateway = request.form.get('pc_default_gateway', '').strip()

   # ตรวจสอบ Switch Config
   switch_score, missing_keywords = check_keywords(user_switch_config, KEYWORDS)

   # ตรวจสอบ PC Config
   pc_correct = (
       user_pc_ip == "192.168.1.10" and
       user_pc_subnet == "255.255.255.0" and
       user_pc_gateway == "192.168.1.1"
   )

   # สร้าง result dictionary
   result = {
       'student_id': username,
       'switch_score': round(switch_score, 2),
       'missing_commands': missing_keywords,
       'pc_status': 'correct' if pc_correct else 'incorrect',
       'status': 'success' if switch_score == 100 and pc_correct else 'partial' if switch_score > 0 or pc_correct else 'failed'
   }

   # อัปเดตลงฐานข้อมูล
   scores_collection.update_one(
       {"username": username, "lab": "Lab 1"},  # filter
       {"$set": {  # update
           "switch_score": f"{switch_score:.2f}/100",
           "pc_status": "ถูกต้อง" if pc_correct else "ไม่ถูกต้อง",
           "missing_keywords": missing_keywords,
           "switch_config": user_switch_config,
           "pc_config": {
               "ip_address": user_pc_ip,
               "subnet_mask": user_pc_subnet,
               "default_gateway": user_pc_gateway
           },
           "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
       }},
       upsert=True  # สร้างเอกสารใหม่หากไม่มี
   )

   return render_template('lab1.html', result=result)