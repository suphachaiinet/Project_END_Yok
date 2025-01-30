import re
from flask import Blueprint, render_template, request, session
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab4_bp = Blueprint('lab4', __name__)

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ Config
# ----------------------------------------------------------------------
def check_config(config, expected_keywords):
    missing = []
    for keyword in expected_keywords:
        if isinstance(keyword, dict):
            for interface, commands in keyword.items():
                interface_block = re.findall(rf"{interface}\s*(.+?)!", config, re.DOTALL)
                if not interface_block or not all(cmd in interface_block[0] for cmd in commands):
                    missing.append(f"{interface}: {', '.join(commands)}")
        elif keyword not in config:
            missing.append(keyword)
    return missing

# ----------------------------------------------------------------------
# ฟังก์ชันตรวจสอบ Spanning Tree Config
# ----------------------------------------------------------------------
def check_spanning_tree_config(spanning_config, expected_config):
    missing_keywords = []
    for key, expected_value in expected_config.items():
        actual_value = re.search(rf"{key}\s+(.+)", spanning_config)
        if not actual_value or expected_value not in actual_value.group(1):
            missing_keywords.append(f"{key}: คาดว่า '{expected_value}'")
    return missing_keywords

# ----------------------------------------------------------------------
# คีย์เวิร์ดเฉลย
# ----------------------------------------------------------------------
EXPECTED_CONFIG_SW1 = [
    "hostname S1",
    "spanning-tree mode pvst",
    {"interface FastEthernet0/1": ["switchport mode trunk"]},
    {"interface Vlan1": ["ip address 192.168.1.1 255.255.255.0"]},
]
EXPECTED_CONFIG_SW2 = [
    "hostname S2",
    "spanning-tree mode pvst",
    {"interface FastEthernet0/2": ["switchport mode trunk"]},
    {"interface Vlan1": ["ip address 192.168.1.2 255.255.255.0"]},
]
EXPECTED_CONFIG_SW3 = [
    "hostname S3",
    "spanning-tree mode pvst",
    {"interface FastEthernet0/3": ["switchport mode trunk"]},
    {"interface Vlan1": ["ip address 192.168.1.3 255.255.255.0"]},
]

EXPECTED_SPANNING_TREE_SW1 = {
    "Fa0/2": "Root FWD",
    "Fa0/4": "Altn BLK",
}
EXPECTED_SPANNING_TREE_SW2 = {
    "Fa0/2": "Desg FWD",
    "Fa0/4": "Desg FWD",
}
EXPECTED_SPANNING_TREE_SW3 = {
    "Fa0/2": "Root FWD",
    "Fa0/4": "Desg FWD",
}

# ----------------------------------------------------------------------
# MongoDB Connection
# ----------------------------------------------------------------------
client = MongoClient('mongodb://localhost:27017/')
db = client['network_lab']
scores_collection = db['lab4_scores']

# ----------------------------------------------------------------------
# Route: /lab4
# ----------------------------------------------------------------------
@lab4_bp.route('/lab4')
def lab4():
    return render_template('lab4.html')

@lab4_bp.route('/check_config/lab4', methods=['POST'])
def check_config_lab4():
    # รับค่าจากฟอร์ม
    config_sw1 = request.form.get('config_sw1', '').strip()
    config_sw2 = request.form.get('config_sw2', '').strip()
    config_sw3 = request.form.get('config_sw3', '').strip()
    spanning_sw1 = request.form.get('spanning_config_sw1', '').strip()
    spanning_sw2 = request.form.get('spanning_config_sw2', '').strip()
    spanning_sw3 = request.form.get('spanning_config_sw3', '').strip()

    # ตรวจสอบ Config
    missing_sw1 = check_config(config_sw1, EXPECTED_CONFIG_SW1)
    missing_sw2 = check_config(config_sw2, EXPECTED_CONFIG_SW2)
    missing_sw3 = check_config(config_sw3, EXPECTED_CONFIG_SW3)

    # ตรวจสอบ Spanning Tree
    spanning_missing_sw1 = check_spanning_tree_config(spanning_sw1, EXPECTED_SPANNING_TREE_SW1)
    spanning_missing_sw2 = check_spanning_tree_config(spanning_sw2, EXPECTED_SPANNING_TREE_SW2)
    spanning_missing_sw3 = check_spanning_tree_config(spanning_sw3, EXPECTED_SPANNING_TREE_SW3)

    # คำนวณคะแนน
    score_sw1 = 100 - (len(missing_sw1) / len(EXPECTED_CONFIG_SW1)) * 100
    spanning_score_sw1 = 100 - (len(spanning_missing_sw1) / len(EXPECTED_SPANNING_TREE_SW1)) * 100

    score_sw2 = 100 - (len(missing_sw2) / len(EXPECTED_CONFIG_SW2)) * 100
    spanning_score_sw2 = 100 - (len(spanning_missing_sw2) / len(EXPECTED_SPANNING_TREE_SW2)) * 100

    score_sw3 = 100 - (len(missing_sw3) / len(EXPECTED_CONFIG_SW3)) * 100
    spanning_score_sw3 = 100 - (len(spanning_missing_sw3) / len(EXPECTED_SPANNING_TREE_SW3)) * 100

    # สร้างผลลัพธ์
    result = f"""
    <h3>SW1</h3>
    <strong>Switch Config:</strong> คะแนน {score_sw1:.2f}% ({', '.join(missing_sw1) if missing_sw1 else 'ถูกต้อง'})<br>
    <strong>Spanning Tree:</strong> คะแนน {spanning_score_sw1:.2f}% ({', '.join(spanning_missing_sw1) if spanning_missing_sw1 else 'ถูกต้อง'})<br><br>

    <h3>SW2</h3>
    <strong>Switch Config:</strong> คะแนน {score_sw2:.2f}% ({', '.join(missing_sw2) if missing_sw2 else 'ถูกต้อง'})<br>
    <strong>Spanning Tree:</strong> คะแนน {spanning_score_sw2:.2f}% ({', '.join(spanning_missing_sw2) if spanning_missing_sw2 else 'ถูกต้อง'})<br><br>

    <h3>SW3</h3>
    <strong>Switch Config:</strong> คะแนน {score_sw3:.2f}% ({', '.join(missing_sw3) if missing_sw3 else 'ถูกต้อง'})<br>
    <strong>Spanning Tree:</strong> คะแนน {spanning_score_sw3:.2f}% ({', '.join(spanning_missing_sw3) if spanning_missing_sw3 else 'ถูกต้อง'})<br><br>
    """

    # บันทึกผลใน MongoDB
    username = session.get('username', 'unknown')
    scores_collection.insert_one({
        "username": username,
        "lab": "Lab 4",
        "result": result,
        "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
    })

    return render_template('lab4.html', result=result)
