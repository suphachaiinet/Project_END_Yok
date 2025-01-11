import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient

# ลองใช้ zoneinfo (Python 3.9+) ถ้า Windows ไม่เจอ Asia/Bangkok ให้ pip install tzdata
try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

# สร้าง Blueprint
lab_bp = Blueprint('lab', __name__)

# โฟลเดอร์ที่เก็บไฟล์เฉลย
CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

def read_config_file(filename):
    """
    อ่านไฟล์เฉลยในโฟลเดอร์ check_config
    เช่น lab1_sw1.txt, lab1_pc1.txt
    """
    file_path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

def check_config(user_config, correct_config):
    """
    ตรวจสอบความถูกต้องหลัก: 
    1) ตัด whitespace ส่วนเกิน (space, tab, newline) ให้เหลือ space เดียว
    2) เปรียบเทียบ string == string
    """
    user_clean = re.sub(r'\s+', ' ', user_config.strip())
    correct_clean = re.sub(r'\s+', ' ', correct_config.strip())
    return user_clean == correct_clean

def check_vlan_and_interface(user_config):
    """
    ตรวจจับคอนฟิกเกิน:
      - ข้ามบรรทัด 'vlan internal allocation policy ascending'
      - ถ้าพบ vlan <num> != 99 => เตือน
      - ถ้าพบ 'interface Vlan<num>' != 99 => เตือน
      - สำหรับพอร์ต Physical (fastethernet0/x หรือ gigabitethernet0/x):
         1) ตรวจว่าพอร์ตอยู่ใน allowed_interfaces หรือไม่ 
         2) ถ้าพอร์ตไม่อนุญาต => แจ้งเตือน 
         3) ถ้าเป็นพอร์ตอนุญาต แต่มีคำสั่ง config ที่ไม่อยู่ใน allowed_commands => แจ้งเตือน
      - หากเจอแค่ '!' (หรือบรรทัดว่างเปล่า) ใน porth ที่ไม่อนุญาต ก็ไม่เตือน (เพราะไม่มีคำสั่ง config จริง)
    """
    extra_warnings = []

    # แยกเป็นบรรทัดดิบ
    lines_raw = user_config.splitlines()
    # ตัดบรรทัดว่างเปล่าออก และ strip() เพื่อลบ space รอบนอก
    lines = [line.strip() for line in lines_raw if line.strip()]

    # เก็บชื่อ interface ปัจจุบัน (None ถ้ายังไม่เจอ interface)
    current_interface = None

    # พอร์ตที่อนุญาต (ปรับตามที่ต้องการ)
    allowed_interfaces = [
        "fastethernet0/1",
        "fastethernet0/24",
        "gigabitethernet0/1",
        "gigabitethernet0/2"
    ]
    # คำสั่งภายใต้ interface ที่อนุญาต
    allowed_commands_under_interface = {
        "switchport access vlan 99",
        "switchport mode access"
    }

    for line_raw in lines:
        line = line_raw.lower()

        # 1) ข้าม: 'vlan internal allocation policy ascending'
        if "vlan internal allocation policy ascending" in line:
            continue

        # 2) ตรวจจับ vlan <num> (เช่น 'vlan 10', 'vlan 1')
        if line.startswith("vlan "):
            parts = line.split()
            if len(parts) == 2:
                vlan_num = parts[1]
                if vlan_num != '99':
                    extra_warnings.append(f"พบ VLAN เกิน: {line_raw}")
            continue

        # 3) หากเป็น interface <something>
        if line.startswith("interface "):
            # เช่น line = 'interface fastethernet0/1'
            current_interface = line[len("interface "):]  # 'fastethernet0/1'
            # ถ้าเป็น interface vlan<num> != 99 => เตือน
            if current_interface.startswith("vlan") and current_interface != "vlan99":
                extra_warnings.append(f"พบ VLAN เกิน: interface {current_interface}")
            continue

        # 4) ถ้ามีคำสั่ง config ใน interface Physical
        #    เช่น 'switchport access vlan 99'
        #    -> เช็คว่า interface อนุญาตไหม
        if current_interface:
            # ถ้าเป็น physical interface
            if (current_interface.startswith("fastethernet") or 
                current_interface.startswith("gigabitethernet")):

                # (4.1) ถ้า interface นี้ไม่อยู่ใน allowed => แจ้งเตือน
                if current_interface not in allowed_interfaces:
                    extra_warnings.append(
                        f"พบการ config เกินบน interface {current_interface}: {line_raw}"
                    )
                else:
                    # (4.2) อยู่ใน allowed_interfaces => เช็คว่าคำสั่งนี้อนุญาตไหม
                    if line_raw.lower() not in allowed_commands_under_interface:
                        extra_warnings.append(
                            f"พบการ config เกินบน interface {current_interface}: {line_raw}"
                        )
    return extra_warnings

# เชื่อมต่อ MongoDB (ปรับตามการตั้งค่า)
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab_scores']

@lab_bp.route('/lab1')
def lab1():
    """
    แสดงหน้า lab1.html
    ซึ่งมีฟอร์มรับ config_switch, config_pc
    """
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1', methods=['POST'])
def check_config_lab1():
    """
    1) รับ config Switch, PC จากฟอร์ม
    2) เปรียบเทียบกับไฟล์เฉลย (lab1_sw1.txt, lab1_pc1.txt)
    3) แบ่งคะแนน Switch/PC
    4) ตรวจจับ config เกิน (check_vlan_and_interface)
    5) บันทึกผลลง MongoDB
    6) ส่งผลลัพธ์ไปแสดงใน lab1.html
    """

    # 1) รับคอนฟิกจากฟอร์ม
    user_switch_config = request.form.get('config_switch', '')
    user_pc_config = request.form.get('config_pc', '')

    # 2) อ่านไฟล์เฉลย
    correct_switch_config = read_config_file('lab1_sw1.txt')  # ในโฟลเดอร์ check_config
    correct_pc_config = read_config_file('lab1_pc1.txt')

    # 3) ตรวจสอบความถูกต้อง (เปรียบเทียบสตริง)
    switch_correct = check_config(user_switch_config, correct_switch_config)
    pc_correct = check_config(user_pc_config, correct_pc_config)

    # 4) แบ่งคะแนน (ตัวอย่าง Switch:70, PC:30)
    switch_total_points = 70
    pc_total_points = 30
    switch_score = switch_total_points if switch_correct else 0
    pc_score = pc_total_points if pc_correct else 0
    total_score = switch_score + pc_score  # สูงสุด 100

    # 5) ตรวจจับคอนฟิกเกิน
    extra_sw_warn = check_vlan_and_interface(user_switch_config)
    extra_pc_warn = check_vlan_and_interface(user_pc_config)
    extra_messages = []
    if extra_sw_warn:
        extra_messages.extend(extra_sw_warn)
    if extra_pc_warn:
        extra_messages.extend(extra_pc_warn)

    # เวลาปัจจุบัน (Asia/Bangkok)
    try:
        bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))
    except:
        import pytz
        tz = pytz.timezone('Asia/Bangkok')
        bangkok_time = datetime.now(tz)

    # ดึง username จาก session (ถ้ามีระบบ login)
    username = session.get('username', 'unknown')

    # 6) บันทึกลง MongoDB
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 1",
        "switch_score": f"{switch_score}/{switch_total_points}",
        "pc_score": f"{pc_score}/{pc_total_points}",
        "total_score": f"{total_score}/100",
        "timestamp": bangkok_time,
        "extra_config": extra_messages
    })

    # 7) สร้างผลลัพธ์
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนน Switch: {switch_score}/{switch_total_points}<br>
    คะแนน PC: {pc_score}/{pc_total_points}<br>
    คะแนนรวม: {total_score}/100<br>
    Switch Configuration: {"ถูกต้อง" if switch_correct else "ผิดพลาด"}<br>
    PC Configuration: {"ถูกต้อง" if pc_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')}
    """

    # ถ้ามีคอนฟิกเกิน
    if extra_messages:
        result += "<hr><strong>พบคอนฟิกเกิน:</strong><br>"
        for warn in extra_messages:
            result += f"- {warn}<br>"

    # ส่งผลลัพธ์ไปแสดงใน lab1.html
    return render_template('lab1.html', result=result)
