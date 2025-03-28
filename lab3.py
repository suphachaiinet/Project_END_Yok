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

lab3_bp = Blueprint('lab3', __name__)

# แก้ไขในส่วน MongoDB Connection ของ lab.py
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']  # ชื่อ database ที่ใช้
scores_collection = db['lab_scores']
users_collection = db['users_all']  # เพิ่มบรรทัดนี้ให้ชัดเจน
lab_keywords_collection = db['lab_keywords']  # เพิ่มเพื่อเชื่อมต่อกับคอลเล็กชันคีย์เวิร์ด

def preprocess_vlan_config(vlan_config):
    """
    จัดรูปแบบผลลัพธ์ของคำสั่ง show vlan brief เพื่อให้ง่ายต่อการประมวลผล
    """
    lines = vlan_config.splitlines()
    processed_lines = []
    current_line = ""

    for line in lines:
        if line.strip():  # ข้ามบรรทัดว่าง
            if re.match(r"^\d+\s+\w+", line):  # ตรวจสอบว่าบรรทัดเริ่มต้นด้วย VLAN ID
                if current_line:  # เพิ่มบรรทัดก่อนหน้าลงในรายการที่ประมวลผลแล้ว
                    processed_lines.append(current_line)
                current_line = line.strip()
            else:
                current_line += " " + line.strip()  # เพิ่มบรรทัดต่อเนื่อง
    if current_line:  # เพิ่มบรรทัดสุดท้ายที่ประมวลผล
        processed_lines.append(current_line)

    return "\n".join(processed_lines)

def check_vlan_config(vlan_config, expected_vlans):
    """
    ตรวจสอบการกำหนดค่า VLAN จากผลลัพธ์ของคำสั่ง show vlan brief
    
    Parameters:
        vlan_config (str): ผลลัพธ์ของคำสั่ง show vlan brief
        expected_vlans (dict): พจนานุกรมที่มี VLAN ID เป็นคีย์และข้อมูล VLAN เป็นค่า
    
    Returns:
        tuple: (รายการ VLAN ที่หายไป, พจนานุกรมของ VLAN ที่ไม่ถูกต้อง)
    """
    missing_vlans = []
    incorrect_vlans = {}

    vlan_config = preprocess_vlan_config(vlan_config)

    for vlan_id, expected_data in expected_vlans.items():
        vlan_info = re.search(
            rf"^{vlan_id}\s+(\w+(?:-\w+)?)\s+active\s+([\s\S]*?)(?=^\d+|\Z)",
            vlan_config,
            re.MULTILINE
        )
        if not vlan_info:
            missing_vlans.append(vlan_id)
        else:
            vlan_name = vlan_info.group(1)
            vlan_ports = re.findall(r"(Fa0/\d+|Gig0/\d+)", vlan_info.group(2) if vlan_info.group(2) else "")

            if vlan_name.lower() != expected_data["name"].lower():  # ตรวจสอบแบบไม่สนใจตัวพิมพ์เล็กหรือใหญ่
                incorrect_vlans[vlan_id] = {
                    "type": "name",
                    "expected": expected_data["name"],
                    "actual": vlan_name
                }

            if set(vlan_ports) != set(expected_data["ports"]):
                incorrect_vlans[vlan_id] = {
                    "type": "ports",
                    "expected_ports": expected_data["ports"],
                    "actual_ports": vlan_ports
                }

    return missing_vlans, incorrect_vlans

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
    clean_interface_block = [cmd.strip('"\'').lower() for cmd in interface_block]
    clean_expected_commands = [cmd.strip('"\'').lower() for cmd in expected_commands]
    
    missing_commands = []
    for cmd in clean_expected_commands:
        found = False
        for block_cmd in clean_interface_block:
            if cmd == block_cmd:
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

def check_pc_config(user_pc_ip, user_pc_subnet, user_pc_gateway, correct_ip, correct_subnet, correct_gateway):
    """
    ตรวจสอบการกำหนดค่า PC
    
    Returns:
    bool: True ถ้าการกำหนดค่าถูกต้อง, False ถ้าไม่ถูกต้อง
    """
    return user_pc_ip == correct_ip and user_pc_subnet == correct_subnet and user_pc_gateway == correct_gateway

@lab3_bp.route('/lab3', methods=['GET', 'POST'])
def lab3():
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

    # ดึงข้อมูลคีย์เวิร์ดจากฐานข้อมูล
    lab_keywords = lab_keywords_collection.find_one({"lab_num": 3})
    
    if not lab_keywords:
        # ถ้ายังไม่มีคีย์เวิร์ด ให้ใช้ค่าเริ่มต้น
        SW1_KEYWORDS = [
            "hostname S1",
            "no ip domain-lookup",
            {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
            {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
            {"interface Vlan1": ["no ip address"]},
            {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
            {"interface Vlan20": ["ip address 192.168.20.11 255.255.255.0"]},
            {"interface Vlan30": ["ip address 192.168.30.11 255.255.255.0"]}
        ]

        SW2_KEYWORDS = [
            "hostname S2",
            "no ip domain-lookup",
            {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
            {"interface FastEthernet0/18": ["switchport access vlan 30", "switchport mode access"]},
            {"interface Vlan1": ["no ip address"]},
            {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]}
        ]

        expected_vlans_sw1 = {
            "1": {"name": "default", "ports": []},
            "10": {"name": "Management", "ports": []},
            "20": {"name": "Sales", "ports": ["Fa0/6"]},
            "30": {"name": "Operations", "ports": []},
            "999": {"name": "ParkingLot", "ports": ["Fa0/2", "Fa0/3", "Fa0/4", "Fa0/5", "Fa0/7", "Fa0/8", "Fa0/9", "Fa0/10", 
                                                "Fa0/11", "Fa0/12", "Fa0/13", "Fa0/14", "Fa0/15", "Fa0/16", "Fa0/17", "Fa0/18", 
                                                "Fa0/19", "Fa0/20", "Fa0/21", "Fa0/22", "Fa0/23", "Fa0/24", "Gig0/1", "Gig0/2"]},
            "1000": {"name": "Native", "ports": []}
        }

        expected_vlans_sw2 = {
            "1": {"name": "default", "ports": []},
            "10": {"name": "Management", "ports": []},
            "20": {"name": "Sales", "ports": []},
            "30": {"name": "Operations", "ports": ["Fa0/18"]},
            "999": {"name": "ParkingLot", "ports": ["Fa0/2", "Fa0/3", "Fa0/4", "Fa0/5", "Fa0/6", "Fa0/7", "Fa0/8", "Fa0/9", 
                                                "Fa0/10", "Fa0/11", "Fa0/12", "Fa0/13", "Fa0/14", "Fa0/15", "Fa0/16", "Fa0/17", 
                                                "Fa0/19", "Fa0/20", "Fa0/21", "Fa0/22", "Fa0/23", "Fa0/24", "Gig0/1", "Gig0/2"]}
        }
        
        pc1_config = {
            "ip": "192.168.20.13",
            "subnet": "255.255.255.0",
            "gateway": "192.168.20.11"
        }
        
        pc2_config = {
            "ip": "192.168.30.13",
            "subnet": "255.255.255.0",
            "gateway": "192.168.30.11"
        }
        
        # บันทึกคีย์เวิร์ดลงฐานข้อมูล
        lab_keywords_collection.insert_one({
            "lab_num": 3,
            "switch1_keywords": SW1_KEYWORDS,
            "switch2_keywords": SW2_KEYWORDS,
            "expected_vlans_sw1": expected_vlans_sw1,
            "expected_vlans_sw2": expected_vlans_sw2,
            "pc1_config": pc1_config,
            "pc2_config": pc2_config,
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))+ timedelta(hours=7)
        })
    else:
        # ใช้คีย์เวิร์ดจากฐานข้อมูล
        SW1_KEYWORDS = lab_keywords.get("switch1_keywords", [])
        SW2_KEYWORDS = lab_keywords.get("switch2_keywords", [])
        expected_vlans_sw1 = lab_keywords.get("expected_vlans_sw1", {})
        expected_vlans_sw2 = lab_keywords.get("expected_vlans_sw2", {})
        pc1_config = lab_keywords.get("pc1_config", {})
        pc2_config = lab_keywords.get("pc2_config", {})

    if request.method == 'POST':
        user_sw1_config = request.form.get('config_switch1', '').strip()
        vlan_config_sw1 = request.form.get('vlan_config_switch1', '').strip()
        user_sw2_config = request.form.get('config_switch2', '').strip()
        vlan_config_sw2 = request.form.get('vlan_config_switch2', '').strip()
        
        user_pc1_ip = request.form.get('pc1_ip_address', '').strip()
        user_pc1_subnet = request.form.get('pc1_subnet_mask', '').strip()
        user_pc1_gateway = request.form.get('pc1_default_gateway', '').strip()
        
        user_pc2_ip = request.form.get('pc2_ip_address', '').strip()
        user_pc2_subnet = request.form.get('pc2_subnet_mask', '').strip()
        user_pc2_gateway = request.form.get('pc2_default_gateway', '').strip()

        # ตรวจสอบการกำหนดค่า
        pc1_correct = check_pc_config(
            user_pc1_ip, user_pc1_subnet, user_pc1_gateway, 
            pc1_config.get("ip", "192.168.20.13"), 
            pc1_config.get("subnet", "255.255.255.0"), 
            pc1_config.get("gateway", "192.168.20.11")
        )
        
        pc2_correct = check_pc_config(
            user_pc2_ip, user_pc2_subnet, user_pc2_gateway, 
            pc2_config.get("ip", "192.168.30.13"), 
            pc2_config.get("subnet", "255.255.255.0"), 
            pc2_config.get("gateway", "192.168.30.11")
        )

        sw1_score, sw1_missing = check_keywords(user_sw1_config, SW1_KEYWORDS)
        sw2_score, sw2_missing = check_keywords(user_sw2_config, SW2_KEYWORDS)

        missing_vlans_sw1, incorrect_vlans_sw1 = check_vlan_config(vlan_config_sw1, expected_vlans_sw1)
        missing_vlans_sw2, incorrect_vlans_sw2 = check_vlan_config(vlan_config_sw2, expected_vlans_sw2)

        vlan_sw1_correct = not missing_vlans_sw1 and not incorrect_vlans_sw1
        vlan_sw2_correct = not missing_vlans_sw2 and not incorrect_vlans_sw2

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
            'vlan_sw1_status': "correct" if vlan_sw1_correct else "incorrect",
            'vlan_sw2_status': "correct" if vlan_sw2_correct else "incorrect",
            'vlan_sw1_details': {
                'missing': missing_vlans_sw1,
                'incorrect': incorrect_vlans_sw1
            },
            'vlan_sw2_details': {
                'missing': missing_vlans_sw2,
                'incorrect': incorrect_vlans_sw2
            },
            'pc1_status': 'correct' if pc1_correct else 'incorrect',
            'pc2_status': 'correct' if pc2_correct else 'incorrect',
            'status': 'success' if (total_score == 100 and pc1_correct and pc2_correct and 
                                  vlan_sw1_correct and vlan_sw2_correct) else 'partial'
        }

        # บันทึกลงฐานข้อมูล
        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 3"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "pc1_status": "ถูกต้อง" if pc1_correct else "ไม่ถูกต้อง",
                    "pc2_status": "ถูกต้อง" if pc2_correct else "ไม่ถูกต้อง",
                    "vlan_sw1_status": "ถูกต้อง" if vlan_sw1_correct else "ไม่ถูกต้อง",
                    "vlan_sw2_status": "ถูกต้อง" if vlan_sw2_correct else "ไม่ถูกต้อง",
                    "configs": {
                        "sw1_config": user_sw1_config,
                        "sw2_config": user_sw2_config,
                        "vlan_sw1_config": vlan_config_sw1,
                        "vlan_sw2_config": vlan_config_sw2,
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
            
            session['lab3_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab3.lab3'))

    # สำหรับ GET request
    result = session.get('lab3_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab3.html', 
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name,
                         active_lab='lab3')