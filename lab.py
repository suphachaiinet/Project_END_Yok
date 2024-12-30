import os
import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient
from zoneinfo import ZoneInfo  # ใช้ zoneinfo เพื่อจัดการ Timezone

lab_bp = Blueprint('lab', __name__)

CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

def read_config_file(filename):
    file_path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

def check_config(user_config, correct_config):
    user_config_cleaned = re.sub(r'\s+', ' ', user_config.strip())
    correct_config_cleaned = re.sub(r'\s+', ' ', correct_config.strip())
    return user_config_cleaned == correct_config_cleaned

client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab_scores']

@lab_bp.route('/lab1')
def lab1():
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1', methods=['POST'])
def check_config_lab1():
    user_switch_config = request.form.get('config_switch', '').strip()
    user_pc_config = request.form.get('config_pc', '').strip()

    correct_switch_config = read_config_file('lab1_sw1.txt')
    correct_pc_config = read_config_file('lab1_pc1.txt')

    switch_correct = check_config(user_switch_config, correct_switch_config)
    pc_correct = check_config(user_pc_config, correct_pc_config)

    switch_score = 50 if switch_correct else 0
    pc_score = 50 if pc_correct else 0
    total_score = switch_score + pc_score

    username = session.get('username', 'unknown')

    # บันทึกค่าเวลาตามเขตเวลา 'Asia/Bangkok'
    bangkok_time = datetime.now(ZoneInfo("Asia/Bangkok"))

    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 1",
        "switch_score": f"{switch_score}%",
        "pc_score": f"{pc_score}%",
        "total_score": f"{total_score}%",
        "timestamp": bangkok_time  # เก็บเวลาตามโซนเอเชีย/กรุงเทพ
    })

    result = f"""
    ชื่อผู้ใช้: {username}<br>
    คะแนนรวม: {total_score}%<br>
    Switch Configuration: {"ถูกต้อง" if switch_correct else "ผิดพลาด"}<br>
    PC Configuration: {"ถูกต้อง" if pc_correct else "ผิดพลาด"}<br>
    <strong>Time (Asia/Bangkok): {bangkok_time.strftime('%Y-%m-%d %H:%M:%S')}</strong>
    """
    return render_template('lab1.html', result=result)
