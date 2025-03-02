import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab_bp = Blueprint('lab', __name__)

# แก้ไขในส่วน MongoDB Connection ของ lab.py
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']
users_collection = db['users_all']
lab_keywords_collection = db['lab_keywords']  # เพิ่มการเชื่อมต่อกับคอลเลกชันคีย์เวิร์ด

def parse_interfaces(config_text):
    """
    แยกคำสั่งตาม interface จากข้อความคอนฟิกทั้งหมด
    
    Parameters:
    config_text (str): ข้อความคอนฟิกทั้งหมด
    
    Returns:
    dict: พจนานุกรมที่มีคีย์เป็นชื่อ interface และค่าเป็นรายการคำสั่งในแต่ละ interface
    """
    interfaces = {}
    current_interface = None
    lines = config_text.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("interface"):
            current_interface = line
            interfaces[current_interface] = []
        elif current_interface and line:
            interfaces[current_interface].append(line)
    
    return interfaces

def check_interface_block(interface_block, expected_commands):
    """
    ตรวจสอบว่าคำสั่งที่ต้องการมีอยู่ใน interface block หรือไม่
    
    Parameters:
    interface_block (list): รายการคำสั่งใน interface
    expected_commands (list): รายการคำสั่งที่ต้องการตรวจสอบ
    
    Returns:
    list: รายการคำสั่งที่ไม่พบใน interface block
    """
    # คำสั่งอาจมีเครื่องหมายคำพูด หรือไม่มีก็ได้ ให้ตัดออก
    clean_interface_block = [cmd.strip('"\'') for cmd in interface_block]
    clean_expected_commands = [cmd.strip('"\'') for cmd in expected_commands]
    
    missing_commands = []
    for cmd in clean_expected_commands:
        found = False
        for block_cmd in clean_interface_block:
            if cmd.lower() == block_cmd.lower():
                found = True
                break
        
        if not found:
            missing_commands.append(cmd)
    
    return missing_commands
def check_keywords(user_config, keywords):
    """
    ตรวจสอบคีย์เวิร์ดในคอนฟิกของผู้ใช้
    
    Parameters:
    user_config (str): คอนฟิกของผู้ใช้
    keywords (list): รายการคีย์เวิร์ดที่ต้องตรวจสอบ
    
    Returns:
    tuple: (คะแนน, รายการคำสั่งที่ไม่พบ)
    """
    user_interfaces = parse_interfaces(user_config)
    missing_keywords = []
    found_keywords = []

    for keyword in keywords:
        if isinstance(keyword, dict):
            # กรณีเป็น interface block
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
            # กรณีเป็นคำสั่งทั่วไป
            keyword_found = False
            for line in user_config.lower().splitlines():
                if keyword.lower() in line:
                    keyword_found = True
                    break
                    
            if keyword_found:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords
def extract_commands_from_running_config(config_text):
    """แยกวิเคราะห์ running-config และดึงเฉพาะคำสั่งที่สำคัญออกมา"""
    extracted_commands = []
    
    # ดึงคำสั่งทั่วไป
    important_commands = [
        "service password-encryption",
        "hostname",
        "no ip domain-lookup"
    ]
    
    for line in config_text.splitlines():
        line = line.strip()
        if any(cmd in line for cmd in important_commands):
            extracted_commands.append(line)
    
    # ดึงการตั้งค่า interface
    interfaces = parse_interfaces(config_text)
    important_interfaces = ["FastEthernet0/24", "GigabitEthernet0/1", "GigabitEthernet0/2", "Vlan99"]
    
    for interface_name, commands in interfaces.items():
        if any(iface in interface_name for iface in important_interfaces):
            extracted_commands.append(interface_name)
            for cmd in commands:
                if any(keyword in cmd for keyword in ["switchport", "ip address"]):
                    extracted_commands.append("  " + cmd)
    
    # ดึง ip default-gateway
    for line in config_text.splitlines():
        line = line.strip()
        if line.startswith("ip default-gateway"):
            extracted_commands.append(line)
    
    return "\n".join(extracted_commands)

def clean_keywords(keyword_text):
    """ทำความสะอาดข้อความคีย์เวิร์ด ลบเครื่องหมาย quotes และวงเล็บ"""
    if isinstance(keyword_text, str):
        # ลบเครื่องหมาย quotes
        return keyword_text.strip('"\'')
    elif isinstance(keyword_text, list):
        # ลบเครื่องหมาย quotes จากแต่ละรายการ
        return [clean_keywords(item) for item in keyword_text]
    elif isinstance(keyword_text, dict):
        # ลบเครื่องหมาย quotes จาก key และ value
        return {clean_keywords(key): clean_keywords(value) for key, value in keyword_text.items()}
    else:
        return keyword_text

def check_keywords(user_config, keywords):
    # ตรวจสอบว่าเป็น running-config ทั้งไฟล์หรือไม่
    if "Building configuration" in user_config and "Current configuration" in user_config:
        # แปลง running-config เป็นคำสั่งที่สำคัญเท่านั้น
        user_config = extract_commands_from_running_config(user_config)
        print("Extracted commands from running-config:", user_config)
    
    # Clean keywords ในกรณีที่มีเครื่องหมาย quotes
    cleaned_keywords = []
    for keyword in keywords:
        if isinstance(keyword, dict):
            cleaned_dict = {}
            for key, value in keyword.items():
                # ลบเครื่องหมาย quotes จาก key
                cleaned_key = key.strip('"\'[]')
                # ลบเครื่องหมาย quotes จาก value
                if isinstance(value, list):
                    cleaned_value = [v.strip('"\'[]') for v in value]
                else:
                    cleaned_value = value
                cleaned_dict[cleaned_key] = cleaned_value
            cleaned_keywords.append(cleaned_dict)
        else:
            # ลบเครื่องหมาย quotes จากคีย์เวิร์ดทั่วไป
            cleaned_keywords.append(str(keyword).strip('"\'[]'))
    
    user_interfaces = parse_interfaces(user_config)
    missing_keywords = []
    found_keywords = []

    for keyword in cleaned_keywords:
        if isinstance(keyword, dict):
            interface_name = list(keyword.keys())[0]
            expected_commands = keyword[interface_name]

            # ตรวจสอบว่ามี interface นี้ในการกำหนดค่าหรือไม่
            matching_interfaces = [name for name in user_interfaces.keys() 
                               if interface_name.lower() in name.lower()]
            
            if matching_interfaces:
                # ใช้ interface แรกที่ตรงกัน
                matching_interface = matching_interfaces[0]
                missing = check_interface_block(user_interfaces[matching_interface], expected_commands)
                if not missing:
                    found_keywords.append(interface_name)
                else:
                    missing_keywords.extend([f"{interface_name}: {cmd}" for cmd in missing])
            else:
                missing_keywords.append(f"{interface_name}: (missing block)")
        else:
            keyword_str = str(keyword).lower()
            if any(keyword_str in line.lower() for line in user_config.splitlines()):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

    total_keywords = len(cleaned_keywords)
    if total_keywords == 0:
        score = 0
    else:
        score = (len(found_keywords) / total_keywords) * 100

    return score, missing_keywords

@lab_bp.route('/lab1', methods=['GET', 'POST'])
def lab1():
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
        username = session.get('username', 'unknown')
        user_switch_config = request.form.get('config_switch', '').strip()

        # PC Config
        user_pc_ip = request.form.get('pc_ip_address', '').strip()
        user_pc_subnet = request.form.get('pc_subnet_mask', '').strip()
        user_pc_gateway = request.form.get('pc_default_gateway', '').strip()

        # ดึงคีย์เวิร์ดจากฐานข้อมูล
        lab1_keywords = lab_keywords_collection.find_one({"lab_num": 1})
        
        if not lab1_keywords:
            # ถ้าไม่มีข้อมูลในฐานข้อมูล ใช้ค่าเริ่มต้น
            default_keywords = [
                "service password-encryption",
                "hostname s1",
                "no ip domain-lookup",
                {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
                {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
                {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
                {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0"]}
            ]
            default_pc = {
                "ip": "192.168.1.10",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.1"
            }
            keywords_to_check = default_keywords
            correct_pc_ip = default_pc["ip"]
            correct_pc_subnet = default_pc["subnet"]
            correct_pc_gateway = default_pc["gateway"]
        else:
            # ใช้คีย์เวิร์ดจากฐานข้อมูล
            keywords_to_check = lab1_keywords.get('switch_keywords', [])
            
            # ดึงข้อมูล PC Config จากฐานข้อมูล
            pc_config = lab1_keywords.get('pc_config', {})
            correct_pc_ip = pc_config.get('ip', '')
            correct_pc_subnet = pc_config.get('subnet', '')
            correct_pc_gateway = pc_config.get('gateway', '')

        # ตรวจสอบ Switch Config
        switch_score, missing_keywords = check_keywords(user_switch_config, keywords_to_check)

        # ตรวจสอบ PC Config
        pc_correct = (
            user_pc_ip == correct_pc_ip and
            user_pc_subnet == correct_pc_subnet and
            user_pc_gateway == correct_pc_gateway
        )

        # สร้าง result dictionary
        result = {
            'student_id': username,
            'first_name': session.get('first_name', 'Unknown'),
            'switch_score': round(switch_score, 2),
            'missing_commands': missing_keywords,
            'pc_status': 'correct' if pc_correct else 'incorrect',
            'status': 'success' if switch_score == 100 and pc_correct else 'partial' if switch_score > 0 or pc_correct else 'failed'
        }

        # บันทึกลงฐานข้อมูลและ session
        try:
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

            # เก็บคะแนนใน session
            session['lab1_score'] = round(switch_score, 2)
            session['lab1_result'] = result
            session.modified = True  # บอกให้ Flask รู้ว่า session ถูกแก้ไข

            print(f"Saved score for {username}: {switch_score}")
        except Exception as e:
            print(f"Error saving score: {e}")

        return redirect(url_for('lab.lab1'))
    
    # กรณี GET
    result = session.get('lab1_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab1.html', 
                     result=result,
                     scores=lab_scores,
                     overall_score=overall_score,
                     first_name=first_name,
                     last_name=last_name,
                     active_lab='lab1')  # เพิ่ม active_lab เพื่อไฮไลท์เมนู

# เพิ่มค่าคงที่เพื่อใช้เป็น fallback หากไม่พบข้อมูลในฐานข้อมูล
DEFAULT_KEYWORDS = [
    "service password-encryption",
    "hostname s1",
    "no ip domain-lookup",
    {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
    {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
    {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0"]}
]