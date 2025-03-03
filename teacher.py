from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from bson import ObjectId
import json

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

# เชื่อมต่อกับ MongoDB
from pymongo import MongoClient

try:
    from lab6 import R1_KEYWORDS as LAB6_R1_KEYWORDS, SW1_KEYWORDS as LAB6_SW1_KEYWORDS, SW2_KEYWORDS as LAB6_SW2_KEYWORDS, EXPECTED_VLANS as LAB6_EXPECTED_VLANS
    from lab7 import R1_KEYWORDS as LAB7_R1_KEYWORDS, SW1_KEYWORDS as LAB7_SW1_KEYWORDS, SW2_KEYWORDS as LAB7_SW2_KEYWORDS, EXPECTED_VLANS as LAB7_EXPECTED_VLANS
except ImportError:
    # Set default values for Lab 6
    LAB6_R1_KEYWORDS = [
        "hostname R1",
        "service password-encryption",
        "no ip domain lookup",
        {"interface GigabitEthernet0/0/1.3": ["description Management Network", "encapsulation dot1Q 3", "ip address 192.168.3.1 255.255.255.0"]},
        {"interface GigabitEthernet0/0/1.4": ["description Operations Network", "encapsulation dot1Q 4", "ip address 192.168.4.1 255.255.255.0"]},
        {"interface GigabitEthernet0/0/1.8": ["description Native VLAN", "encapsulation dot1Q 8 native"]}
    ]
    
    LAB6_SW1_KEYWORDS = [
        "hostname S1",
        "service password-encryption",
        "spanning-tree mode rapid-pvst",
        {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
        {"interface FastEthernet0/6": ["switchport access vlan 3", "switchport mode access"]},
        {"interface Vlan3": ["ip address 192.168.3.11 255.255.255.0"]},
        "ip default-gateway 192.168.3.1"
    ]
    
    LAB6_SW2_KEYWORDS = [
        "hostname S2",
        "service password-encryption",
        "spanning-tree mode rapid-pvst",
        {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
        {"interface FastEthernet0/18": ["switchport access vlan 4", "switchport mode access"]},
        {"interface Vlan3": ["ip address 192.168.3.12 255.255.255.0"]},
        "ip default-gateway 192.168.3.1"
    ]
    
    LAB6_EXPECTED_VLANS = {
        "3": "Management",
        "4": "Operations",
        "8": "Native"
    }
    
    # Set default values for Lab 7
    LAB7_R1_KEYWORDS = [
        "hostname R1",
        "service password-encryption",
        "no ip domain lookup",
        {"interface GigabitEthernet0/0/1.10": ["description Management Network", "encapsulation dot1Q 10", "ip address 192.168.10.1 255.255.255.0"]},
        {"interface GigabitEthernet0/0/1.20": ["description Sales network", "encapsulation dot1Q 20", "ip address 192.168.20.1 255.255.255.0"]},
        {"interface GigabitEthernet0/0/1.30": ["description Operations Network", "encapsulation dot1Q 30", "ip address 192.168.30.1 255.255.255.0"]},
        {"interface GigabitEthernet0/0/1.1000": ["description Native VLAN", "encapsulation dot1Q 1000 native"]}
    ]
    
    LAB7_SW1_KEYWORDS = [
        "hostname S1",
        "service password-encryption",
        "spanning-tree mode rapid-pvst",
        {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
        {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
        {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
        "ip default-gateway 192.168.10.1"
    ]
    
    LAB7_SW2_KEYWORDS = [
        "hostname S2",
        "service password-encryption",
        "spanning-tree mode rapid-pvst", 
        {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
        {"interface FastEthernet0/18": ["switchport access vlan 30", "switchport mode access"]},
        {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]},
        "ip default-gateway 192.168.10.1"
    ]
    
    LAB7_EXPECTED_VLANS = {
        "10": "Management",
        "20": "Sales",
        "30": "Operations",
        "1000": "Native"
    }

teacher_bp = Blueprint('teacher', __name__)

mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']
students_collection = db['students']
scores_collection = db['lab_scores']
users_collection = db['users_all']
# คอลเลคชั่นใหม่สำหรับเก็บ keyword ของแต่ละแล็บ
lab_keywords_collection = db['lab_keywords']

# ดึงข้อมูลจำนวนนักศึกษาและคะแนนทั้งหมด
@teacher_bp.route('/students')
def students():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลนักศึกษาทั้งหมด
    students = list(students_collection.find())
    all_scores = list(scores_collection.find())
    
    # คำนวณสถิติรวม
    total_score = 0
    num_scores = 0
    for score in all_scores:
        try:
            score_value = float(score['switch_score'].split('/')[0])
            total_score += score_value
            num_scores += 1
        except:
            continue
    
    avg_score = total_score / num_scores if num_scores > 0 else 0
    total_students = len(students)
    completed_students = len(set(score['username'] for score in all_scores))
    completion_rate = (completed_students / total_students * 100) if total_students > 0 else 0
    
    # คำนวณคะแนนสำหรับแต่ละนักศึกษา
    for student in students:
        student_scores = [s for s in all_scores if s['username'] == student['username']]
        total_score = 0
        completed_labs = 0
        
        for score in student_scores:
            try:
                lab_score = float(score['switch_score'].split('/')[0])
                total_score += lab_score
                if lab_score >= 60:  # ถือว่าทำเสร็จหากได้มากกว่า 60%
                    completed_labs += 1
            except Exception as e:
                print(f"Error processing score: {e}")
        
        student['avg_score'] = total_score / 16 if student_scores else 0
        student['completed_labs'] = completed_labs
        student['completion_rate'] = (completed_labs / 16) * 100 if completed_labs > 0 else 0
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # คำนวณเวลาส่งงานล่าสุด
    latest_submission = max([score.get('timestamp', datetime.min) for score in all_scores], default=None)
    
    return render_template('teacher_students.html', 
                          students=students,
                          first_name=first_name,
                          last_name=last_name,
                          total_students=total_students,
                          avg_score=avg_score,
                          completion_rate=completion_rate,
                          last_activity_time=latest_submission)

# แสดงสถิติภาพรวม
@teacher_bp.route('/stats')
def stats():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลนักศึกษาทั้งหมด
    total_students = students_collection.count_documents({})
    
    # ดึงข้อมูลคะแนนทั้งหมด
    all_scores = list(scores_collection.find())
    
    # คำนวณสถิติต่างๆ
    labs_data = {}
    for i in range(1, 17):
        lab_scores = [s for s in all_scores if s.get('lab') == f'Lab {i}']
        
        if lab_scores:
            total_score = sum([float(s['switch_score'].split('/')[0]) for s in lab_scores if 'switch_score' in s])
            avg_score = total_score / len(lab_scores) if lab_scores else 0
            
            labs_data[i] = {
                'total_submissions': len(lab_scores),
                'avg_score': avg_score,
                'completion_rate': sum([1 for s in lab_scores if float(s['switch_score'].split('/')[0]) >= 60]) / len(lab_scores) * 100 if lab_scores else 0
            }
        else:
            labs_data[i] = {
                'total_submissions': 0,
                'avg_score': 0,
                'completion_rate': 0
            }
    
    # หาแล็บที่มีอัตราการทำเสร็จสูงสุดและต่ำสุด
    completion_rates = [(lab_num, lab_data['completion_rate']) for lab_num, lab_data in labs_data.items()]
    
    # คำนวณค่าเฉลี่ยรวม
    all_scores_values = []
    for lab_scores in [s for s in all_scores if 'switch_score' in s]:
        try:
            score_value = float(lab_scores['switch_score'].split('/')[0])
            all_scores_values.append(score_value)
        except:
            continue
    
    overall_avg_score = sum(all_scores_values) / len(all_scores_values) if all_scores_values else 0
    
    highest_completion = max(completion_rates, key=lambda x: x[1]) if completion_rates else (0, 0)
    lowest_completion = min(completion_rates, key=lambda x: x[1]) if completion_rates else (0, 0)
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('teacher_stats.html', 
                          labs_data=labs_data,
                          first_name=first_name,
                          last_name=last_name,
                          total_students=total_students,
                          overall_avg_score=overall_avg_score,
                          highest_completion_lab=highest_completion[0],
                          highest_completion_rate=highest_completion[1],
                          lowest_completion_lab=lowest_completion[0],
                          lowest_completion_rate=lowest_completion[1])

def format_keywords_for_display(keywords):
    """
    จัดรูปแบบ keywords เพื่อแสดงผลในหน้าเว็บ
    
    Parameters:
    keywords (list): รายการ keywords ที่เก็บใน MongoDB
    
    Returns:
    str: ข้อความ keywords ที่จัดรูปแบบสำหรับแสดงผลแล้ว
    """
    formatted_text = ""
    
    for item in keywords:
        if isinstance(item, dict):
            for interface, commands in item.items():
                # เขียนชื่อ interface
                formatted_text += f"{interface}\n"
                # เขียนคำสั่งย่อย
                for cmd in commands:
                    formatted_text += f"  {cmd}\n"
            formatted_text += "\n"  # เพิ่มบรรทัดว่างระหว่าง interface
        else:
            # เขียนคำสั่งปกติ
            formatted_text += f"{item}\n"
    
    return formatted_text.rstrip()

# แสดงหน้าจัดการแล็บ
@teacher_bp.route('/lab/<int:lab_num>')
def lab_management(lab_num):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูล keyword ของแล็บนี้
    lab_keywords = lab_keywords_collection.find_one({"lab_num": lab_num})
    
    # ตัวแปรสำหรับเก็บ text ของ keywords
    switch_keywords_text = ""
    switch1_keywords_text = ""
    switch2_keywords_text = ""
    switch3_keywords_text = ""
    router_keywords_text = ""
    expected_vlans_text = ""
    general_keywords_text = ""

    if not lab_keywords:
        # ถ้ายังไม่มีคีย์เวิร์ด ให้ใช้ค่าเริ่มต้นจากไฟล์ lab.py หรือ lab<n>.py
        if lab_num == 1:
            # ตัวอย่างสำหรับ Lab 1 จากไฟล์ lab.py
            default_keywords = [
                "service password-encryption",
                "hostname s1",
                "no ip domain-lookup",
                {"interface FastEthernet0/24": ["switchport access vlan 99", "switchport mode access"]},
                {"interface GigabitEthernet0/1": ["switchport access vlan 99", "switchport mode access"]},
                {"interface GigabitEthernet0/2": ["switchport access vlan 99", "switchport mode access"]},
                {"interface Vlan99": ["ip address 192.168.1.2 255.255.255.0", "ip default-gateway 192.168.1.1"]}
            ]
            pc_config = {
                "ip": "192.168.1.10",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.1"
            }
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "switch_keywords": default_keywords,
                "pc_config": pc_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "switch_keywords": default_keywords,
                "pc_config": pc_config
            }
            
            switch_keywords_text = format_keywords_for_display(default_keywords)
            
        elif lab_num == 2:
            # ตัวอย่างสำหรับ Lab 2 จากไฟล์ lab2.py
            sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
            ]
            
            pc1_config = {
                "ip": "192.168.10.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.10.1"
            }
            
            pc2_config = {
                "ip": "192.168.10.4",
                "subnet": "255.255.255.0",
                "gateway": "192.168.10.1"
            }
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "switch1_keywords": sw1_keywords,
                "switch2_keywords": sw2_keywords,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "switch1_keywords": sw1_keywords,
                "switch2_keywords": sw2_keywords,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config
            }
            
            switch1_keywords_text = format_keywords_for_display(sw1_keywords)
            switch2_keywords_text = format_keywords_for_display(sw2_keywords)
            
        elif lab_num == 6:
            # ค่าเริ่มต้นสำหรับ Lab 6
            router_keywords = LAB6_R1_KEYWORDS
            switch1_keywords = LAB6_SW1_KEYWORDS
            switch2_keywords = LAB6_SW2_KEYWORDS
            expected_vlans = LAB6_EXPECTED_VLANS
            
            # PC configurations for Lab 6
            pca_config = {
                "ip": "192.168.3.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.3.1"
            }
            
            pcb_config = {
                "ip": "192.168.4.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.4.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "router_keywords": router_keywords,
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "router_keywords": router_keywords,
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }
            
            router_keywords_text = format_keywords_for_display(router_keywords)
            switch1_keywords_text = format_keywords_for_display(switch1_keywords)
            switch2_keywords_text = format_keywords_for_display(switch2_keywords)
            
            # แปลง expected_vlans เป็น text
            for vlan_id, vlan_name in expected_vlans.items():
                expected_vlans_text += f"{vlan_id}:{vlan_name}\n"
                
        elif lab_num == 7:
            # ค่าเริ่มต้นสำหรับ Lab 7
            router_keywords = LAB7_R1_KEYWORDS
            switch1_keywords = LAB7_SW1_KEYWORDS
            switch2_keywords = LAB7_SW2_KEYWORDS
            expected_vlans = LAB7_EXPECTED_VLANS
            
            # PC configurations for Lab 7
            pca_config = {
                "ip": "192.168.20.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.20.1"
            }
            
            pcb_config = {
                "ip": "192.168.30.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.30.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "router_keywords": router_keywords,
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "router_keywords": router_keywords,
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }
            
            router_keywords_text = format_keywords_for_display(router_keywords)
            switch1_keywords_text = format_keywords_for_display(switch1_keywords)
            switch2_keywords_text = format_keywords_for_display(switch2_keywords)
            
            # แปลง expected_vlans เป็น text
            for vlan_id, vlan_name in expected_vlans.items():
                expected_vlans_text += f"{vlan_id}:{vlan_name}\n"
                
        else:
            # สำหรับแล็บอื่นๆ
            default_keywords = []
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "general_keywords": default_keywords,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "general_keywords": default_keywords
            }
            
            general_keywords_text = format_keywords_for_display(default_keywords)
    else:
        # ถ้ามีข้อมูลอยู่แล้วในฐานข้อมูล ให้ดึงมาแสดง
        if lab_num == 1:
            switch_keywords = lab_keywords.get('switch_keywords', [])
            switch_keywords_text = format_keywords_for_display(switch_keywords)
        elif lab_num == 2:
            switch1_keywords = lab_keywords.get('switch1_keywords', [])
            switch2_keywords = lab_keywords.get('switch2_keywords', [])
            switch1_keywords_text = format_keywords_for_display(switch1_keywords)
            switch2_keywords_text = format_keywords_for_display(switch2_keywords)
        elif lab_num == 6 or lab_num == 7:
            router_keywords = lab_keywords.get('router_keywords', [])
            switch1_keywords = lab_keywords.get('switch1_keywords', [])
            switch2_keywords = lab_keywords.get('switch2_keywords', [])
            expected_vlans = lab_keywords.get('expected_vlans', {})
            
            router_keywords_text = format_keywords_for_display(router_keywords)
            switch1_keywords_text = format_keywords_for_display(switch1_keywords)
            switch2_keywords_text = format_keywords_for_display(switch2_keywords)
            
            # แปลง expected_vlans เป็น text
            for vlan_id, vlan_name in expected_vlans.items():
                expected_vlans_text += f"{vlan_id}:{vlan_name}\n"
        else:
            general_keywords = lab_keywords.get('general_keywords', [])
            general_keywords_text = format_keywords_for_display(general_keywords)

    # ดึงข้อมูลการส่งแล็บของนักศึกษาทั้งหมด
    submissions = list(scores_collection.find({"lab": f"Lab {lab_num}"}))
    
    # ดึงข้อมูลนักศึกษาแต่ละคน
    students_data = []
    for submission in submissions:
        username = submission['username']
        student = students_collection.find_one({"username": username})
        
        if student:
            try:
                score = float(submission['switch_score'].split('/')[0])
                status = 'completed' if score >= 60 else 'in_progress'
                status_text = 'เสร็จสมบูรณ์' if score >= 60 else 'กำลังทำ'
            except Exception:
                score = 0
                status = 'in_progress'
                status_text = 'กำลังทำ'
            
            students_data.append({
                'student_id': username,
                'name': f"{student.get('first_name', '')} {student.get('last_name', '')}",
                'score': score,
                'status': status,
                'status_text': status_text,
                'timestamp': submission.get('timestamp', 'Unknown')
            })
    
    # เรียงลำดับตามคะแนน (มากไปน้อย)
    students_data.sort(key=lambda x: x['score'], reverse=True)
    
    # คำนวณข้อมูลสถิติ
    completed_count = sum(1 for student in students_data if student['status'] == 'completed')
    total_students = students_collection.count_documents({})
    completion_rate = (completed_count / total_students) * 100 if total_students > 0 else 0
    
    scores = [student['score'] for student in students_data]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0
    
    # ชื่อแล็บ
    lab_titles = {
        1: "Basic Switch Configuration",
        2: "Configure VLANs and Trunking",
        3: "Implement VLANs and Trunking",
        4: "Redundant Links",
        5: "Rapid PVST+",
        6: "Router-on-a-Stick Inter-VLAN",
        7: "Inter-VLAN Routing",
        8: "EtherChannel",
        9: "PPP Authentication",
        10: "Standard IPv4 ACLs",
        11: "Extended IPv4 ACLs",
        12: "DHCPv4",
        13: "DHCPv6",
        14: "NAT",
        15: "HSRP",
        16: "Switch Security"
    }
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('lab_management.html',
                           lab_num=lab_num,
                           lab_title=lab_titles.get(lab_num, f"Lab {lab_num}"),
                           students=students_data,
                           completed_count=completed_count,
                           total_students=total_students,
                           completion_rate=round(completion_rate, 2),
                           avg_score=round(avg_score, 2),
                           max_score=round(max_score, 2),
                           min_score=round(min_score, 2),
                           # Keywords for all lab types
                           switch_keywords_text=switch_keywords_text,
                           switch1_keywords_text=switch1_keywords_text,
                           switch2_keywords_text=switch2_keywords_text,
                           switch3_keywords_text=switch3_keywords_text,
                           router_keywords_text=router_keywords_text,
                           expected_vlans_text=expected_vlans_text,
                           general_keywords_text=general_keywords_text,
                           # PC configurations 
                           # keywords.get('pc_config', {}),
                           pc1_config=lab_keywords.get('pc1_config', {}),
                           pc2_config=lab_keywords.get('pc2_config', {}),
                           pca_config=lab_keywords.get('pca_config', {}),
                           pcb_config=lab_keywords.get('pcb_config', {}),
                           active_lab=lab_num,
                           first_name=first_name,
                           last_name=last_name)

# ดูรายละเอียดการส่งงานของนักศึกษา
@teacher_bp.route('/submission/<int:lab_num>/<student_id>')
def view_submission(lab_num, student_id):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลนักศึกษา
    student = students_collection.find_one({"username": student_id})
    
    if not student:
        flash('ไม่พบข้อมูลนักศึกษา', 'danger')
        return redirect(url_for('teacher.lab_management', lab_num=lab_num))
    
    # ดึงข้อมูลการส่งงาน
    submission = scores_collection.find_one({"username": student_id, "lab": f"Lab {lab_num}"})
    
    if not submission:
        flash('ไม่พบข้อมูลการส่งงาน', 'danger')
        return redirect(url_for('teacher.lab_management', lab_num=lab_num))
    
    # คำนวณคะแนนและสถานะ
    try:
        score = float(submission['switch_score'].split('/')[0])
        status = 'completed' if score >= 60 else 'in_progress'
        status_text = 'เสร็จสมบูรณ์' if score >= 60 else 'กำลังทำ'
    except Exception:
        score = 0
        status = 'in_progress'
        status_text = 'กำลังทำ'
    
    submission['score'] = score
    submission['status'] = status
    submission['status_text'] = status_text
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('view_submission.html',
                          lab_num=lab_num,
                          student=student,
                          submission=submission,
                          first_name=first_name,
                          last_name=last_name)

# อัพเดทคะแนนด้วยตนเอง
@teacher_bp.route('/update_grade', methods=['POST'])
def update_grade():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    student_id = request.form.get('student_id')
    lab_num = request.form.get('lab_num')
    manual_score = request.form.get('manual_score')
    
    try:
        manual_score = float(manual_score)
        if manual_score < 0 or manual_score > 100:
            raise ValueError("Score must be between 0 and 100")
    except ValueError:
        flash('คะแนนต้องเป็นตัวเลขระหว่าง 0-100', 'danger')
        return redirect(url_for('teacher.view_submission', lab_num=lab_num, student_id=student_id))
    
    # อัพเดทคะแนนในฐานข้อมูล
    scores_collection.update_one(
        {"username": student_id, "lab": f"Lab {lab_num}"},
        {"$set": {
            "switch_score": f"{manual_score:.2f}/100",
            "manual_graded": True,
            "manual_graded_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }}
    )
    
    flash('อัพเดทคะแนนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('teacher.view_submission', lab_num=lab_num, student_id=student_id))

# ลบการส่งงาน
@teacher_bp.route('/delete_submission', methods=['POST'])
def delete_submission():
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    student_id = request.form.get('student_id')
    lab_num = request.form.get('lab_num')
    
    # ลบข้อมูลการส่งงานจากฐานข้อมูล
    scores_collection.delete_one({"username": student_id, "lab": f"Lab {lab_num}"})
    
    flash('ลบการส่งงานเรียบร้อยแล้ว', 'success')
    return redirect(url_for('teacher.lab_management', lab_num=lab_num))


# อัพเดทคีย์เวิร์ด
@teacher_bp.route('/lab/<int:lab_num>/update', methods=['POST'])
def update_keywords(lab_num):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        if lab_num == 1:
            # อัพเดทสำหรับ Lab 1
            switch_keywords_text = request.form.get('switch_keywords', '')
            pc_ip = request.form.get('pc_ip', '')
            pc_subnet = request.form.get('pc_subnet', '')
            pc_gateway = request.form.get('pc_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            switch_keywords = parse_keywords_from_text(switch_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "switch_keywords": switch_keywords,
                    "pc_config": {
                        "ip": pc_ip,
                        "subnet": pc_subnet,
                        "gateway": pc_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
        elif lab_num == 2:
            # อัพเดทสำหรับ Lab 2
            switch1_keywords_text = request.form.get('switch1_keywords', '')
            switch2_keywords_text = request.form.get('switch2_keywords', '')
            pc1_ip = request.form.get('pc1_ip', '')
            pc1_subnet = request.form.get('pc1_subnet', '')
            pc1_gateway = request.form.get('pc1_gateway', '')
            pc2_ip = request.form.get('pc2_ip', '')
            pc2_subnet = request.form.get('pc2_subnet', '')
            pc2_gateway = request.form.get('pc2_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            switch1_keywords = parse_keywords_from_text(switch1_keywords_text)
            switch2_keywords = parse_keywords_from_text(switch2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "pc1_config": {
                        "ip": pc1_ip,
                        "subnet": pc1_subnet,
                        "gateway": pc1_gateway
                    },
                    "pc2_config": {
                        "ip": pc2_ip,
                        "subnet": pc2_subnet,
                        "gateway": pc2_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        elif lab_num == 6 or lab_num == 7:
            # อัพเดทสำหรับ Lab 6 และ 7
            router_keywords_text = request.form.get('router_keywords', '')
            switch1_keywords_text = request.form.get('switch1_keywords', '')
            switch2_keywords_text = request.form.get('switch2_keywords', '')
            expected_vlans_text = request.form.get('expected_vlans', '')
            
            # PC A
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            
            # PC B
            pcb_ip = request.form.get('pcb_ip', '')
            pcb_subnet = request.form.get('pcb_subnet', '')
            pcb_gateway = request.form.get('pcb_gateway', '')
            
            # แปลงข้อความเป็นคีย์เวิร์ด
            router_keywords = parse_keywords_from_text(router_keywords_text)
            switch1_keywords = parse_keywords_from_text(switch1_keywords_text)
            switch2_keywords = parse_keywords_from_text(switch2_keywords_text)
            
            # แปลง expected_vlans_text เป็น dict
            expected_vlans = {}
            for line in expected_vlans_text.strip().split('\n'):
                if ':' in line:
                    vlan_id, vlan_name = line.split(':', 1)
                    expected_vlans[vlan_id.strip()] = vlan_name.strip()
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "router_keywords": router_keywords,
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "expected_vlans": expected_vlans,
                    "pca_config": {
                        "ip": pca_ip,
                        "subnet": pca_subnet,
                        "gateway": pca_gateway
                    },
                    "pcb_config": {
                        "ip": pcb_ip,
                        "subnet": pcb_subnet,
                        "gateway": pcb_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        else:
            # อัพเดทสำหรับแล็บอื่นๆ
            general_keywords_text = request.form.get('general_keywords', '')
            general_keywords = parse_keywords_from_text(general_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "general_keywords": general_keywords,
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        
        # ลบการส่งงานทั้งหมดในแล็บนี้
        delete_result = scores_collection.delete_many({"lab": f"Lab {lab_num}"})
        deleted_count = delete_result.deleted_count
        
        flash(f'อัพเดทคีย์เวิร์ดเรียบร้อยแล้ว และลบการส่งงาน {deleted_count} รายการ', 'success')
    except Exception as e:
        print(f"Error updating keywords: {str(e)}")
        flash(f'เกิดข้อผิดพลาดในการอัพเดทคีย์เวิร์ด: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.lab_management', lab_num=lab_num))

def parse_keywords_from_text(text):
    """
    แปลงข้อความเป็นรายการคีย์เวิร์ดตามรูปแบบที่ใช้ในการตรวจสอบ
    
    Parameters:
    text (str): ข้อความที่ประกอบด้วยคีย์เวิร์ดและคำสั่งใน interface
    
    Returns:
    list: รายการคีย์เวิร์ดในรูปแบบที่ใช้ในการตรวจสอบ
    """
    keywords = []
    current_interface = None
    interface_commands = []
    
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('interface'):
            # เก็บ interface ก่อนหน้า (ถ้ามี)
            if current_interface and interface_commands:
                keywords.append({current_interface: interface_commands})
            
            # เริ่มต้นบล็อก interface ใหม่
            current_interface = line
            interface_commands = []
        elif line.startswith(' ') and current_interface:
            # คำสั่งในบล็อก interface
            interface_commands.append(line.strip())
        else:
            # ถ้าเป็นบรรทัดปกติที่ไม่ใช่คำสั่งใน interface
            # และมี interface ที่กำลังทำงานอยู่ ให้จบ interface นั้นก่อน
            if current_interface and interface_commands:
                keywords.append({current_interface: interface_commands})
                current_interface = None
                interface_commands = []
            
            # คีย์เวิร์ดปกติ
            keywords.append(line)
    
    # เพิ่ม interface สุดท้าย (ถ้ามี)
    if current_interface and interface_commands:
        keywords.append({current_interface: interface_commands})
    
    return keywords