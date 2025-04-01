import os
import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime, timedelta
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab2_bp = Blueprint('lab2', __name__)

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

def extract_commands_from_running_config(config_text, switch_num=None):
    """แยกวิเคราะห์ running-config และดึงเฉพาะคำสั่งที่สำคัญออกมา"""
    extracted_commands = []
    
    # ดึงคำสั่งทั่วไป
    important_commands = []
    if switch_num == 1 or switch_num is None:
        important_commands.extend([
            "hostname S1",
            "no ip domain-lookup"
        ])
    elif switch_num == 2:
        important_commands.extend([
            "hostname S2"
        ])
    
    for line in config_text.splitlines():
        line = line.strip()
        if any(cmd in line for cmd in important_commands):
            extracted_commands.append(line)
    
    # ดึงการตั้งค่า interface
    interfaces = parse_interfaces(config_text)
    important_interfaces = []
    
    if switch_num == 1 or switch_num is None:
        important_interfaces = ["FastEthernet0/1", "FastEthernet0/6", "Vlan1", "Vlan99"]
    elif switch_num == 2:
        important_interfaces = ["FastEthernet0/1", "FastEthernet0/18", "Vlan1", "Vlan99"]
    
    for interface_name, commands in interfaces.items():
        if any(iface in interface_name for iface in important_interfaces):
            extracted_commands.append(interface_name)
            for cmd in commands:
                if any(keyword in cmd for keyword in ["switchport", "ip address", "no ip address"]):
                    extracted_commands.append("  " + cmd)
    
    return "\n".join(extracted_commands)
def check_keywords(user_config, keywords):
    # ตรวจสอบว่าเป็น running-config ทั้งไฟล์หรือไม่
    if "Building configuration" in user_config and "Current configuration" in user_config:
        # แปลง running-config เป็นคำสั่งที่สำคัญเท่านั้น
        user_config = extract_commands_from_running_config(user_config)
    
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

def check_keywords(user_config, keywords, switch_num=None):
    # ตรวจสอบว่าเป็น running-config ทั้งไฟล์หรือไม่
    if "Building configuration" in user_config and "Current configuration" in user_config:
        # แปลง running-config เป็นคำสั่งที่สำคัญเท่านั้น
        user_config = extract_commands_from_running_config(user_config, switch_num)
        print(f"Extracted commands for Switch {switch_num}:", user_config)
    
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

def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway, correct_ip, correct_subnet, correct_gateway):
    pc_correct = (
        user_pc_ip == correct_ip and
        user_pc_subnet == correct_subnet and
        user_pc_gateway == correct_gateway
    )
    return pc_correct

@lab2_bp.route('/lab2', methods=['GET', 'POST'])
def lab2():
    if 'username' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
        return redirect(url_for('login'))

    username = session.get('username')
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
        user_sw1_config = request.form.get('config_switch1', '').strip()
        user_sw2_config = request.form.get('config_switch2', '').strip()
        
        user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
        user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
        user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
        
        user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
        user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
        user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

        # ดึงคีย์เวิร์ดจากฐานข้อมูล
        lab2_keywords = lab_keywords_collection.find_one({"lab_num": 2})
        
        if not lab2_keywords:
            # ถ้าไม่มีข้อมูลในฐานข้อมูล ใช้ค่าเริ่มต้น
            default_sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
            ]
            
            default_sw2_keywords = [
                "hostname S2",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
            ]
            
            default_pc1 = {
                "ip": "192.168.10.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.10.1"
            }
            
            default_pc2 = {
                "ip": "192.168.10.4",
                "subnet": "255.255.255.0",
                "gateway": "192.168.10.1"
            }
            
            sw1_keywords_to_check = default_sw1_keywords
            sw2_keywords_to_check = default_sw2_keywords
            correct_pc1_ip = default_pc1["ip"]
            correct_pc1_subnet = default_pc1["subnet"]
            correct_pc1_gateway = default_pc1["gateway"]
            correct_pc2_ip = default_pc2["ip"]
            correct_pc2_subnet = default_pc2["subnet"]
            correct_pc2_gateway = default_pc2["gateway"]
        else:
            # ใช้คีย์เวิร์ดจากฐานข้อมูล
            sw1_keywords_to_check = lab2_keywords.get('switch1_keywords', [])
            sw2_keywords_to_check = lab2_keywords.get('switch2_keywords', [])
            
            # ดึงข้อมูล PC Config จากฐานข้อมูล
            pc1_config = lab2_keywords.get('pc1_config', {})
            correct_pc1_ip = pc1_config.get('ip', '')
            correct_pc1_subnet = pc1_config.get('subnet', '')
            correct_pc1_gateway = pc1_config.get('gateway', '')
            
            pc2_config = lab2_keywords.get('pc2_config', {})
            correct_pc2_ip = pc2_config.get('ip', '')
            correct_pc2_subnet = pc2_config.get('subnet', '')
            correct_pc2_gateway = pc2_config.get('gateway', '')

        # ตรวจสอบ configurations
        sw1_score, sw1_missing = check_keywords(user_sw1_config, sw1_keywords_to_check, 1)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, sw2_keywords_to_check, 2)
        
        pc1_correct = check_pc_config(
            user_pc1_ip, user_pc1_subnet, user_pc1_gateway,
            correct_pc1_ip, correct_pc1_subnet, correct_pc1_gateway
        )
        
        pc2_correct = check_pc_config(
            user_pc2_ip, user_pc2_subnet, user_pc2_gateway,
            correct_pc2_ip, correct_pc2_subnet, correct_pc2_gateway
        )

        # คำนวณคะแนนรวม
        total_score = (sw1_score + sw2_score) / 2

        # สร้าง result object
        result = {
            'student_id': username,
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'total_score': round(total_score, 2),
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'pc1_status': 'correct' if pc1_correct else 'incorrect',
            'pc2_status': 'correct' if pc2_correct else 'incorrect',
            'status': 'success' if total_score == 100 and pc1_correct and pc2_correct else 'partial'
        }

        # บันทึกลงฐานข้อมูล
        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 2"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pc1_status": "ถูกต้อง" if pc1_correct else "ไม่ถูกต้อง",
                    "pc2_status": "ถูกต้อง" if pc2_correct else "ไม่ถูกต้อง",
                    "sw1_missing": sw1_missing,
                    "sw2_missing": sw2_missing,
                    "configs": {
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "pc1_config": {
                            "ip": user_pc1_ip,
                            "subnet": user_pc1_subnet,
                            "gateway": user_pc1_gateway
                        },
                        "pc2_config": {
                            "ip": user_pc2_ip,
                            "subnet": user_pc2_subnet,
                            "gateway": user_pc2_gateway
                        }
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))+ timedelta(hours=7)
                }},
                upsert=True
            )
            
            session['lab2_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab2.lab2'))

    # สำหรับ GET request
    result = session.get('lab2_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab2.html',
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                         active_lab='lab2')

# เพิ่มค่าคงที่เพื่อใช้เป็น fallback หากไม่พบข้อมูลในฐานข้อมูล
DEFAULT_SW1_KEYWORDS = [
    "hostname S1",
    "no ip domain-lookup",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
]

DEFAULT_SW2_KEYWORDS = [
    "hostname S2",
    {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
    {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
    {"interface Vlan1": ["no ip address"]},
    {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
]