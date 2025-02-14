import re
from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

lab4_bp = Blueprint('lab4', __name__)

# MongoDB Connection
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_lab']
scores_collection = db['lab_scores']
users_collection = db['users_all']

def check_config(config, expected_keywords):
    missing = []
    found = []
    for keyword in expected_keywords:
        if isinstance(keyword, dict):
            for interface, commands in keyword.items():
                interface_block = re.findall(rf"{interface}\s*(.+?)!", config, re.DOTALL)
                if not interface_block or not all(cmd in interface_block[0] for cmd in commands):
                    missing.append(f"{interface}: {', '.join(commands)}")
                else:
                    found.append(interface)
        elif keyword not in config:
            missing.append(keyword)
        else:
            found.append(keyword)
    
    total_keywords = len(expected_keywords)
    score = (len(found) / total_keywords) * 100 if total_keywords > 0 else 0
    return score, missing

def check_spanning_tree_config(spanning_config, expected_config):
    missing = []
    found = []
    for key, expected_value in expected_config.items():
        actual_value = re.search(rf"{key}\s+(.+)", spanning_config)
        if not actual_value or expected_value not in actual_value.group(1):
            missing.append(f"{key}: expected '{expected_value}'")
        else:
            found.append(key)
    
    total_items = len(expected_config)
    score = (len(found) / total_items) * 100 if total_items > 0 else 0
    return score, missing

# Expected configurations
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

@lab4_bp.route('/lab4', methods=['GET', 'POST'])
def lab4():
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
        config_sw1 = request.form.get('config_sw1', '').strip()
        config_sw2 = request.form.get('config_sw2', '').strip()
        config_sw3 = request.form.get('config_sw3', '').strip()
        spanning_sw1 = request.form.get('spanning_config_sw1', '').strip()
        spanning_sw2 = request.form.get('spanning_config_sw2', '').strip()
        spanning_sw3 = request.form.get('spanning_config_sw3', '').strip()

        # Check configurations
        sw1_score, sw1_missing = check_config(config_sw1, EXPECTED_CONFIG_SW1)
        sw2_score, sw2_missing = check_config(config_sw2, EXPECTED_CONFIG_SW2)
        sw3_score, sw3_missing = check_config(config_sw3, EXPECTED_CONFIG_SW3)

        # Check spanning tree
        spanning_score_sw1, spanning_missing_sw1 = check_spanning_tree_config(spanning_sw1, EXPECTED_SPANNING_TREE_SW1)
        spanning_score_sw2, spanning_missing_sw2 = check_spanning_tree_config(spanning_sw2, EXPECTED_SPANNING_TREE_SW2)
        spanning_score_sw3, spanning_missing_sw3 = check_spanning_tree_config(spanning_sw3, EXPECTED_SPANNING_TREE_SW3)

        # Calculate total scores
        total_score = (sw1_score + sw2_score + sw3_score +
                      spanning_score_sw1 + spanning_score_sw2 + spanning_score_sw3) / 6

        # Create result object
        result = {
            'student_id': username,
            'total_score': round(total_score, 2),
            'sw1_score': round(sw1_score, 2),
            'sw2_score': round(sw2_score, 2),
            'sw3_score': round(sw3_score, 2),
            'spanning_score_sw1': round(spanning_score_sw1, 2),
            'spanning_score_sw2': round(spanning_score_sw2, 2),
            'spanning_score_sw3': round(spanning_score_sw3, 2),
            'sw1_missing': sw1_missing,
            'sw2_missing': sw2_missing,
            'sw3_missing': sw3_missing,
            'spanning_missing_sw1': spanning_missing_sw1,
            'spanning_missing_sw2': spanning_missing_sw2,
            'spanning_missing_sw3': spanning_missing_sw3,
            'status': 'success' if total_score == 100 else 'partial'
        }

        try:
            scores_collection.update_one(
                {"username": username, "lab": "Lab 4"},
                {"$set": {
                    "switch_score": f"{total_score:.2f}/100",
                    "sw1_score": f"{sw1_score:.2f}/100",
                    "sw2_score": f"{sw2_score:.2f}/100",
                    "sw3_score": f"{sw3_score:.2f}/100",
                    "spanning_score_sw1": f"{spanning_score_sw1:.2f}/100",
                    "spanning_score_sw2": f"{spanning_score_sw2:.2f}/100",
                    "spanning_score_sw3": f"{spanning_score_sw3:.2f}/100",
                    "configs": {
                        "sw1_config": config_sw1,
                        "sw2_config": config_sw2,
                        "sw3_config": config_sw3,
                        "spanning_sw1": spanning_sw1,
                        "spanning_sw2": spanning_sw2,
                        "spanning_sw3": spanning_sw3
                    },
                    "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
            session['lab4_result'] = result
            session.modified = True
            
        except Exception as e:
            print(f"Error saving score: {e}")
            
        return redirect(url_for('lab4.lab4'))

    # สำหรับ GET request
    result = session.get('lab4_result')
    user = users_collection.find_one({"username": username})
    
    # ถ้าไม่พบข้อมูลผู้ใช้ ใช้ข้อมูลจาก session แทน
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab4.html', 
                         result=result,
                         scores=lab_scores,
                         overall_score=overall_score,
                         first_name=first_name,
                         last_name=last_name)