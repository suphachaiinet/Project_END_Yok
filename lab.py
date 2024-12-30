import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo  # สำหรับเวลาไทย (Python 3.9+)

lab_bp = Blueprint('lab', __name__)

# กำหนดโฟลเดอร์เก็บไฟล์เฉลย
CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

# ฟังก์ชันอ่านไฟล์เฉลย
def read_config_file(filename):
    file_path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

# ฟังก์ชันตรวจสอบความถูกต้องหลัก โดยตัด whitespace เกินด้วย regex
def check_config(user_config, correct_config):
    """
    1) ตัด whitespace (space/tab/newline) ที่ซ้ำกันให้เหลือ space เดียว
    2) เปรียบเทียบแบบ string == string
    """
    user_config_cleaned = re.sub(r'\s+', ' ', user_config.strip())
    correct_config_cleaned = re.sub(r'\s+', ' ', correct_config.strip())
    return user_config_cleaned == correct_config_cleaned

# ฟังก์ชันตรวจจับ VLAN/Interface เกิน
def check_vlan_and_interface(user_config):
    """
    ตัวอย่าง:
    - ถ้าพบคำว่า 'vlan' แต่ไม่ใช่ 'vlan 99' => ถือว่ามี VLAN เกิน
    - ถ้าพบ 'interface ' ที่ไม่ใช่ 'interface Vlan99' หรือ interface FastEthernet0/24
      => ถือว่า interface เกิน
    ปรับแก้ logic ตามที่ต้องการ
    """
    extra_warnings = []
    lines = [line.strip().lower() for line in user_config.splitlines() if line.strip()]

    for line in lines:
        if "vlan" in line and "vlan 99" not in line:
            extra_warnings.append(f"พบ VLAN เกิน: {line}")
        # ตัวอย่าง: อนุญาตแค่ interface vlan99, fastethernet0/24
        if line.startswith("interface ") and not any(sub in line for sub in ["vlan99", "fastethernet0/24"]):
            extra_warnings.append(f"พบ interface เกิน: {line}")

    return extra_warnings

# เชื่อมต่อ MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab_scores']

@lab_bp.route('/lab1')
def lab1():
    """
    แสดงหน้า lab1.html
    """
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1', methods=['POST'])
def check_config_lab1():
    """
    1) รับค่าการตั้งค่า Switch, PC
    2) ตรวจสอบความถูกต้องหลัก (check_config)
    3) ตรวจจับ VLAN/Interface เกิน (check_vlan_and_interface)
    4) บันทึกคะแนนเป็น % + เวลาไทยใน MongoDB
    5) ส่งผลลัพธ์กลับไปแสดง
    """
    # รับค่าที่ผู้ใช้กรอก
    user_switch_config = request.form.get('config_switch', '').strip()
    user_pc_config = request.form.get('config_pc', '').strip()

    # อ่านค่าที่ถูกต้องจากไฟล์เฉลย
    correct_switch_config = read_config_file('lab1_sw1.txt')
    correct_pc_config = read_config_file('lab1_pc1.txt')

    # ตรวจสอบความถูกต้องหลัก
    switch_correct = check_config(user_switch_config, correct_switch_config)
    pc_correct = check_config(user_pc_config, correct_pc_config)

    # คำนวณคะแนนเป็น %
    switch_score = 50 if switch_correct else 0
    pc_score = 50 if pc_correct else 0
    total_score = switch_score + pc_score  # 0-100

    # ตรวจจับคอนฟิกเกิน
    extra_sw_warn = check_vlan_and_interface(user_switch_config)
    extra_pc_warn = check_vlan_and_interface(user_pc_config)
    extra_messages = []
    if extra_sw_warn:
        extra_messages.extend(extra_sw_warn)
    if extra_pc_warn:
        extra_messages.extend(extra_pc_warn)

    # ดึง username จาก session (ถ้าคุณมีระบบ login)
    username = session.get('username', 'unknown')

    # เวลาไทย
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # บันทึกลง DB
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 1",
        "switch_score": f"{switch_score}%",
        "pc_score": f"{pc_score}%",
        "total_score": f"{total_score}%",
        "timestamp": bangkok_time,
        "extra_config": extra_messages
    })

    # สร้างผลลัพธ์
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนนรวม: {total_score}%<br>
    Switch Configuration: {"ถูกต้อง" if switch_correct else "ผิดพลาด"}<br>
    PC Configuration: {"ถูกต้อง" if pc_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    if extra_messages:
        result += "<hr><strong>พบคอนฟิกเกิน:</strong><br>"
        for warn in extra_messages:
            result += f"- {warn}<br>"

    # ส่งผลลัพธ์กลับไปแสดงในหน้า lab1.html
    return render_template('lab1.html', result=result)
