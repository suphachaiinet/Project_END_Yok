import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo  # สำหรับเวลาไทย (Python 3.9+), ถ้าเวอร์ชันต่ำกว่านี้ใช้ pytz

# สร้าง Blueprint สำหรับ Lab 6
lab6_bp = Blueprint('lab6', __name__)

# โฟลเดอร์เก็บไฟล์เฉลย (config) ของ lab6
CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

def read_config_file(filename):
    """ อ่านไฟล์เฉลยจากโฟลเดอร์ check_config/ """
    file_path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

def check_config(user_config, correct_config):
    """
    เปรียบเทียบค่า config ของผู้ใช้กับค่าที่ถูกต้อง:
    1) ลดรูป whitespace (space/tab/newline) ให้เหลือ space เดียว
    2) เปรียบเทียบ string
    """
    user_config_cleaned = re.sub(r'\s+', ' ', user_config.strip())
    correct_config_cleaned = re.sub(r'\s+', ' ', correct_config.strip())
    return user_config_cleaned == correct_config_cleaned

# เชื่อมต่อ MongoDB (กำหนดตามค่าจริงของคุณ)
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab6_scores']  # แยก Collection สำหรับ Lab 2

@lab6_bp.route('/lab6')
def lab6():
    """ แสดงหน้า lab6.html """
    return render_template('lab6.html')

@lab6_bp.route('/check_config/lab6', methods=['POST'])
def check_config_lab6():
    """
    รับค่าการตั้งค่า Switch, PC จากฟอร์มใน lab6.html
    ตรวจสอบความถูกต้อง
    บันทึกคะแนนลงฐานข้อมูล (เป็นเปอร์เซ็นต์)
    ส่งผลลัพธ์ไปแสดงใน lab6.html
    """
    # รับค่าที่ผู้ใช้กรอก
    user_switch_config = request.form.get('config_switch', '').strip()
    user_pc_config = request.form.get('config_pc', '').strip()

    # อ่านค่าที่ถูกต้องจากไฟล์ (อยู่ใน check_config/lab6_sw1.txt, lab6_pc1.txt)
    correct_switch_config = read_config_file('lab6_sw1.txt')
    correct_pc_config = read_config_file('lab6_pc1.txt')

    # ตรวจสอบความถูกต้อง
    switch_correct = check_config(user_switch_config, correct_switch_config)
    pc_correct = check_config(user_pc_config, correct_pc_config)

    # คำนวณคะแนน (สมมติให้ Switch 50, PC 50)
    switch_score = 50 if switch_correct else 0
    pc_score = 50 if pc_correct else 0
    total_score = switch_score + pc_score

    # ดึง username จาก session (กรณีคุณมีระบบ Login)
    username = session.get('username', 'unknown')

    # เวลาปัจจุบันตาม Timezone ไทย
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    # บันทึกลง MongoDB
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 6",
        "switch_score": f"{switch_score}%",
        "pc_score": f"{pc_score}%",
        "total_score": f"{total_score}%",
        "timestamp": bangkok_time
    })

    # ผลลัพธ์ที่จะส่งไปแสดง
    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนนรวม: {total_score}%<br>
    Switch Configuration: {"ถูกต้อง" if switch_correct else "ผิดพลาด"}<br>
    PC Configuration: {"ถูกต้อง" if pc_correct else "ผิดพลาด"}<br>
    เวลาบันทึก: {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Bangkok)
    """

    return render_template('lab6.html', result=result)
