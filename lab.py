import os
from flask import Blueprint, render_template, request

# กำหนด Blueprint
lab_bp = Blueprint('lab', __name__)

# เส้นทางไปยังโฟลเดอร์ check_config
CONFIG_FOLDER = os.path.join(os.getcwd(), 'check_config')

# ฟังก์ชันอ่านไฟล์การตั้งค่า
def read_config_file(filename):
    file_path = os.path.join(CONFIG_FOLDER, filename)
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

@lab_bp.route('/lab1')
def lab1():
    return render_template('lab1.html')

@lab_bp.route('/check_config/lab1_sw1', methods=['POST'])
def check_config_lab1_sw1():
    user_config = request.form['config_switch']
    correct_config = read_config_file('lab1_sw1.txt')  # อ่านค่าที่ถูกต้องจากไฟล์
    result = ""

    if user_config.strip() == correct_config:
        result = "Switch Configuration ถูกต้อง!"
    else:
        result = "Switch Configuration ผิดพลาด!"
    
    return render_template('lab1.html', result=result)

@lab_bp.route('/check_config/lab1_pc1', methods=['POST'])
def check_config_lab1_pc1():
    user_config = request.form['config_pc']
    correct_config = read_config_file('lab1_pc1.txt')  # อ่านค่าที่ถูกต้องจากไฟล์
    result = ""

    if user_config.strip() == correct_config:
        result = "PC Configuration ถูกต้อง!"
    else:
        result = "PC Configuration ผิดพลาด!"
    
    return render_template('lab1.html', result=result)
