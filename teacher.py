from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from bson import ObjectId
import json

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

teacher_bp = Blueprint('teacher', __name__)

# เชื่อมต่อกับ MongoDB
from pymongo import MongoClient

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
    
    # คำนวณอัตราการทำเสร็จรวม
    completed_students = len(set(score['username'] for score in all_scores))
    completion_rate = (completed_students / total_students * 100) if total_students > 0 else 0
    
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
                          avg_score=overall_avg_score,
                          completion_rate=completion_rate,  # เพิ่มบรรทัดนี้
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
    pc_config = {}
    pca_config = {}
    pcb_config = {}
    pcc_config = {}
    pc1_config = {}
    pc2_config = {}
    pc_a_config = {}
    pc_c_config = {}
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
        elif lab_num == 2:
            # ตัวอย่างสำหรับ Lab 2 จากไฟล์ lab2.py
            sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
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
        
        elif lab_num == 3:
            # ตัวอย่างสำหรับ Lab 3 - Implement VLANs and Trunking
            sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
                {"interface Vlan20": ["ip address 192.168.20.11 255.255.255.0"]},
                {"interface Vlan30": ["ip address 192.168.30.11 255.255.255.0"]}
            ]
            
            sw2_keywords = [
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
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans_sw1": expected_vlans_sw1,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans_sw1": expected_vlans_sw1,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config
            }
            
        elif lab_num == 4:
            # ตัวอย่างสำหรับ Lab 4 - Redundant Links
            sw1_keywords = [
                "hostname S1",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/1": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.1 255.255.255.0"]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/2": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.2 255.255.255.0"]}
            ]
            
            sw3_keywords = [
                "hostname S3",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/3": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.3 255.255.255.0"]}
            ]
            
            spanning_tree_sw1 = {
                "Fa0/2": "Root FWD",
                "Fa0/4": "Altn BLK"
            }
            
            spanning_tree_sw2 = {
                "Fa0/2": "Desg FWD",
                "Fa0/4": "Desg FWD"
            }
            
            spanning_tree_sw3 = {
                "Fa0/2": "Root FWD",
                "Fa0/4": "Desg FWD"
            }
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "sw3_keywords": sw3_keywords,
                "spanning_tree_sw1": spanning_tree_sw1,
                "spanning_tree_sw2": spanning_tree_sw2,
                "spanning_tree_sw3": spanning_tree_sw3,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "sw3_keywords": sw3_keywords,
                "spanning_tree_sw1": spanning_tree_sw1,
                "spanning_tree_sw2": spanning_tree_sw2,
                "spanning_tree_sw3": spanning_tree_sw3
            }
            
        elif lab_num == 5:
            # ตัวอย่างสำหรับ Lab 5 - Rapid PVST+
            sw1_keywords = [
                "hostname S1",
                "spanning-tree mode rapid-pvst",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access", 
                                            "spanning-tree portfast", "spanning-tree bpduguard enable"]},
                {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                "spanning-tree mode rapid-pvst",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
            ]
            
            sw3_keywords = [
                "hostname S3",
                "spanning-tree mode rapid-pvst",
                "spanning-tree portfast default",
                "spanning-tree portfast bpduguard default",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 10", "switchport mode access"]},
                {"interface Vlan99": ["ip address 192.168.1.13 255.255.255.0"]}
            ]
            
            pca_config = {
                "ip": "192.168.0.2",
                "subnet": "255.255.255.0"
            }
            
            pcc_config = {
                "ip": "192.168.0.3",
                "subnet": "255.255.255.0"
            }
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "sw3_keywords": sw3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "sw3_keywords": sw3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config
            }
            
        elif lab_num == 6:
            # ตัวอย่างสำหรับ Lab 6 - Router-on-a-Stick Inter-VLAN
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                "no ip domain lookup",
                {"interface GigabitEthernet0/0/1.3": ["description Management Network", "encapsulation dot1Q 3", "ip address 192.168.3.1 255.255.255.0"]},
                {"interface GigabitEthernet0/0/1.4": ["description Operations Network", "encapsulation dot1Q 4", "ip address 192.168.4.1 255.255.255.0"]},
                {"interface GigabitEthernet0/0/1.8": ["description Native VLAN", "encapsulation dot1Q 8 native"]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                "spanning-tree mode rapid-pvst",
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 3", "switchport mode access"]},
                {"interface Vlan3": ["ip address 192.168.3.11 255.255.255.0"]},
                "ip default-gateway 192.168.3.1"
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption",
                "spanning-tree mode rapid-pvst",
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 3,4,8", "switchport trunk native vlan 8", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 4", "switchport mode access"]},
                {"interface Vlan3": ["ip address 192.168.3.12 255.255.255.0"]},
                "ip default-gateway 192.168.3.1"
            ]
            
            expected_vlans = {
                "3": "Management",
                "4": "Operations",
                "8": "Native"
            }
            
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
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }

        # เพิ่มกรณี Lab 7 - Inter-VLAN routing
        elif lab_num == 7:
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                {"interface GigabitEthernet0/0/1.10": ["description Management Network", "encapsulation dot1Q 10", "ip address 192.168.10.1 255.255.255.0"]},
                {"interface GigabitEthernet0/0/1.20": ["description Sales network", "encapsulation dot1Q 20", "ip address 192.168.20.1 255.255.255.0"]},
                {"interface GigabitEthernet0/0/1.30": ["description Operations Network", "encapsulation dot1Q 30", "ip address 192.168.30.1 255.255.255.0"]},
                {"interface GigabitEthernet0/0/1.1000": ["description Native VLAN", "encapsulation dot1Q 1000 native"]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                "spanning-tree mode rapid-pvst",
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
                {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
                "ip default-gateway 192.168.10.1"
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption",
                "spanning-tree mode rapid-pvst", 
                {"interface FastEthernet0/1": ["switchport trunk allowed vlan 10,20,30,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 30", "switchport mode access"]},
                {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]},
                "ip default-gateway 192.168.10.1"
            ]
            
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
            
            expected_vlans = {
                "10": "Management",
                "20": "Sales",
                "30": "Operations",
                "1000": "Native"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }
        # เพิ่มกรณี Lab 8 - EtherChannel
        elif lab_num == 8:
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                {"interface Port-channel1": ["switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/1": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/2": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
                {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption",
                {"interface Port-channel1": ["switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/1": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/2": ["channel-group 1 mode active", "switchport trunk allowed vlan 10,20,1000", "switchport trunk native vlan 1000", "switchport mode trunk"]},
                {"interface FastEthernet0/18": ["switchport access vlan 20", "switchport mode access"]},
                {"interface Vlan10": ["ip address 192.168.10.12 255.255.255.0"]}
            ]
            
            expected_vlans = {
                "10": "Management",
                "20": "Sales",
                "1000": "Native"
            }
            
            expected_vlans_sw2 = {
                "10": "Management",
                "20": "Clients",
                "1000": "Native"
            }
            
            pca_config = {
                "ip": "192.168.20.3",
                "subnet": "255.255.255.0"
            }
            
            pcb_config = {
                "ip": "192.168.20.4",
                "subnet": "255.255.255.0"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }
        # เพิ่มกรณี Lab 9 - PPP Authentication
        elif lab_num == 9:
            r1_keywords = [
                "hostname Branch1",
                "service password-encryption",
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.1 255.255.255.252", 
                    "encapsulation ppp", 
                    "ppp authentication chap",
                    "clock rate 128000"
                ]},
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.1.1 255.255.255.0"
                ]},
                "username Central password",
                {"router ospf 1": [
                    "network 10.1.1.0 0.0.0.3 area 0",
                    "network 192.168.1.0 0.0.0.255 area 0"
                ]}
            ]
            
            r2_keywords = [
                "hostname Central",
                "service password-encryption",
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.2 255.255.255.252", 
                    "encapsulation ppp", 
                    "ppp authentication chap"
                ]},
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.2 255.255.255.252", 
                    "encapsulation ppp", 
                    "ppp authentication chap",
                    "clock rate 128000"
                ]},
                {"interface Loopback0": [
                    "ip address 209.165.200.225 255.255.255.224"
                ]},
                "username Branch3 password",
                "username Branch1 password",
                {"router ospf 1": [
                    "network 10.1.1.0 0.0.0.3 area 0",
                    "network 10.2.2.0 0.0.0.3 area 0",
                    "default-information originate"
                ]},
                "ip route 0.0.0.0 0.0.0.0 Loopback0"
            ]
            
            r3_keywords = [
                "hostname Branch3",
                "service password-encryption",
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.1 255.255.255.252", 
                    "encapsulation ppp", 
                    "ppp authentication chap"
                ]},
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.3.1 255.255.255.0"
                ]},
                "username Central password",
                {"router ospf 1": [
                    "network 10.2.2.0 0.0.0.3 area 0",
                    "network 192.168.3.0 0.0.0.255 area 0"
                ]}
            ]
            
            pca_config = {
                "ip": "192.168.1.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.1"
            }
            
            pcc_config = {
                "ip": "192.168.3.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.3.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config
            }
        # เพิ่มกรณี Lab 10 - Standard IPv4 ACLs
        elif lab_num == 10:
            r1_keywords = [
                "hostname R1",
                "no service password-encryption",
                {"interface Loopback0": [
                    "ip address 192.168.20.1 255.255.255.0"
                ]},
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.10.1 255.255.255.0",
                    "ip access-group BRANCH-OFFICE-POLICY out"
                ]},
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.1 255.255.255.252",
                    "clock rate 128000"
                ]},
                {"router rip": [
                    "version 2",
                    "network 10.1.1.0",
                    "network 192.168.10.0",
                    "network 192.168.20.0"
                ]},
                {"ip access-list standard BRANCH-OFFICE-POLICY": [
                    "permit 192.168.30.3",
                    "permit 192.168.40.0 0.0.0.255",
                    "permit 209.165.200.224 0.0.0.31",
                    "deny any"
                ]}
            ]
            
            r2_keywords = [
                "hostname ISP",
                "no service password-encrypt",
                {"interface Loopback0": [
                    "ip address 209.165.200.225 255.255.255.224"
                ]},
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.2 255.255.255.252"
                ]},
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.2 255.255.255.252",
                    "clock rate 128000"
                ]},
                {"router rip": [
                    "version 2",
                    "network 10.1.1.0",
                    "network 10.2.2.0",
                    "network 209.165.200.224"
                ]}
            ]
            
            r3_keywords = [
                "hostname R3",
                "no service password-encryption",
                {"interface Loopback0": [
                    "ip address 192.168.40.1 255.255.255.0"
                ]},
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.30.1 255.255.255.0",
                    "ip access-group 1 out"
                ]},
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.1 255.255.255.252"
                ]},
                {"router rip": [
                    "version 2",
                    "network 10.2.2.0",
                    "network 192.168.30.0",
                    "network 192.168.40.0"
                ]},
                "access-list 1 remark Allow R1 LANs Access",
                "access-list 1 permit 192.168.10.0 0.0.0.255",
                "access-list 1 permit 192.168.20.0 0.0.0.255",
                "access-list 1 deny any"
            ]
            
            sw1_keywords = [
                "hostname S1",
                "no service password-encryption",
                {"interface Vlan1": [
                    "ip address 192.168.10.11 255.255.255.0"
                ]},
                "ip default-gateway 192.168.10.1"
            ]
            
            sw3_keywords = [
                "hostname S3",
                "no service password-encryption",
                {"interface Vlan1": [
                    "ip address 192.168.30.11 255.255.255.0"
                ]},
                "ip default-gateway 192.168.30.1"
            ]
            
            pca_config = {
                "ip": "192.168.10.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.10.1"
            }
            
            pcc_config = {
                "ip": "192.168.30.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.30.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "sw1_keywords": sw1_keywords,
                "sw3_keywords": sw3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })

            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "sw1_keywords": sw1_keywords,
                "sw3_keywords": sw3_keywords,
                "pca_config": pca_config,
                "pcc_config": pcc_config
            }
        # เพิ่มกรณี Lab 11 - Extended IPv4 ACLs
        elif lab_num == 11:
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                {"interface Loopback1": [
                    "ip address 172.16.1.1 255.255.255.0"
                ]},
                {"interface GigabitEthernet0/0/1.20": [
                    "description Management Network",
                    "encapsulation dot1Q 20",
                    "ip address 10.20.0.1 255.255.255.0"
                ]},
                {"interface GigabitEthernet0/0/1.30": [
                    "description Operations Network",
                    "encapsulation dot1Q 30",
                    "ip address 10.30.0.1 255.255.255.0",
                    "ip access-group 102 in"
                ]},
                {"interface GigabitEthernet0/0/1.40": [
                    "description Sales Network",
                    "encapsulation dot1Q 40",
                    "ip address 10.40.0.1 255.255.255.0",
                    "ip access-group 101 in"
                ]},
                {"interface GigabitEthernet0/0/1.1000": [
                    "description Native VLAN",
                    "encapsulation dot1Q 1000 native"
                ]},
                "access-list 101 remark ACL 101 fulfills policies 1, 2, and 3",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq 22",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq www",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.30.0.1 eq www",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.40.0.1 eq www",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 eq 443",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.30.0.1 eq 443",
                "access-list 101 deny tcp 10.40.0.0 0.0.0.255 host 10.40.0.1 eq 443",
                "access-list 101 deny icmp 10.40.0.0 0.0.0.255 10.20.0.0 0.0.0.255 echo",
                "access-list 101 deny icmp 10.40.0.0 0.0.0.255 10.30.0.0 0.0.0.255 echo",
                "access-list 101 permit ip any any",
                "access-list 102 remark ACL 102 fulfills policy 4",
                "access-list 102 deny icmp 10.30.0.0 0.0.0.255 10.40.0.0 0.0.0.255 echo",
                "access-list 102 permit ip any any"
            ]
            
            r2_keywords = [
                "hostname R2",
                "service password-encryption",
                {"interface GigabitEthernet0/0/1": [
                    "ip address 10.20.0.4 255.255.255.0"
                ]},
                "ip route 0.0.0.0 0.0.0.0 10.20.0.1"
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                {"interface Vlan20": [
                    "ip address 10.20.0.2 255.255.255.0"
                ]},
                "ip default-gateway 10.20.0.1"
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption",
                {"interface Vlan20": [
                    "ip address 10.20.0.3 255.255.255.0"
                ]},
                {"interface FastEthernet0/1": [
                    "switchport trunk allowed vlan 20,30,40,1000",
                    "switchport trunk native vlan 1000",
                    "switchport mode trunk"
                ]},
                {"interface FastEthernet0/5": [
                    "switchport access vlan 20",
                    "switchport mode access"
                ]},
                {"interface FastEthernet0/18": [
                    "switchport access vlan 40",
                    "switchport mode access"
                ]},
                "ip default-gateway 10.20.0.1"
            ]
            
            expected_vlans = {
                "20": "Management", 
                "30": "Operations", 
                "40": "Sales",
                "999": "ParkingLot",
                "1000": "Native"
            }
            
            pca_config = {
                "ip": "10.30.0.10",
                "subnet": "255.255.255.0",
                "gateway": "10.30.0.1"
            }
            
            pcb_config = {
                "ip": "10.40.0.10",
                "subnet": "255.255.255.0",
                "gateway": "10.40.0.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "expected_vlans": expected_vlans,
                "pca_config": pca_config,
                "pcb_config": pcb_config
            }

        elif lab_num == 12:
            # คีย์เวิร์ดสำหรับ Lab 12 - DHCPv4
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                {"interface GigabitEthernet0/0/0": [
                    "ip address 10.0.0.1 255.255.255.252"
                ]},
                {"interface GigabitEthernet0/0/1.100": [
                    "description Connected to Client Network",
                    "encapsulation dot1Q 100",
                    "ip address 192.168.1.1 255.255.255.192"
                ]},
                {"interface GigabitEthernet0/0/1.200": [
                    "description Connected to Management Network", 
                    "encapsulation dot1Q 200",
                    "ip address 192.168.1.65 255.255.255.224"
                ]},
                "ip dhcp excluded-address 192.168.1.1 192.168.1.5",
                "ip dhcp excluded-address 192.168.1.97 192.168.1.101",
                {"ip dhcp pool R1_Client_LAN": [
                    "network 192.168.1.0 255.255.255.192",
                    "domain-name ccna-lab.com",
                    "default-router 192.168.1.1",
                    "lease 2 12 30"
                ]},
                {"ip dhcp pool R2_Client_LAN": [
                    "network 192.168.1.96 255.255.255.240",
                    "default-router 192.168.1.97", 
                    "domain-name ccna-lab.com",
                    "lease 2 12 30"
                ]}
            ]
            
            r2_keywords = [
                "hostname R2",
                "service password-encryption",
                {"interface GigabitEthernet0/0/0": [
                    "ip address 10.0.0.2 255.255.255.252"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "ip address 192.168.1.97 255.255.255.240",
                    "ip helper-address 10.0.0.1"
                ]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                {"interface Vlan200": [
                    "ip address 192.168.1.66 255.255.255.224"
                ]},
                "ip default-gateway 192.168.1.65",
                {"interface FastEthernet0/5": [
                    "switchport trunk allowed vlan 100,200,1000",
                    "switchport trunk native vlan 1000",
                    "switchport mode trunk"
                ]},
                {"interface FastEthernet0/6": [
                    "switchport access vlan 100",
                    "switchport mode access"
                ]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption",
                {"interface Vlan1": [
                    "ip address 192.168.1.98 255.255.255.240"
                ]},
                "ip default-gateway 192.168.1.97"
            ]
            
            pc_a_config = {
                "ip": "192.168.1.3",
                "subnet": "255.255.255.192",
                "gateway": "192.168.1.1"
            }
            
            pc_b_config = {
                "ip": "192.168.1.100",
                "subnet": "255.255.255.240",
                "gateway": "192.168.1.97"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config
            }
            
        elif lab_num == 13:
            # คีย์เวิร์ดสำหรับ Lab 13 - DHCPv6
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                "ipv6 unicast-routing",
                {"ipv6 dhcp pool R1-STATELESS": [
                    "dns-server 2001:DB8:ACAD::254",
                    "domain-name STATELESS.com"
                ]},
                {"ipv6 dhcp pool R2-STATEFUL": [
                    "address prefix 2001:DB8:ACAD:3:AAAA::/80",
                    "dns-server 2001:DB8:ACAD::254",
                    "domain-name STATEFUL.com"
                ]},
                {"interface GigabitEthernet0/0/0": [
                    "ipv6 address 2001:DB8:ACAD:2::1/64",
                    "ipv6 address FE80::1 link-local",
                    "ipv6 dhcp server R2-STATEFUL"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "ipv6 address 2001:DB8:ACAD:1::1/64",
                    "ipv6 address FE80::1 link-local",
                    "ipv6 nd other-config-flag",
                    "ipv6 dhcp server R1-STATELESS"
                ]},
                "ipv6 route ::/0 2001:DB8:ACAD:2::2"
            ]
            
            r2_keywords = [
                "hostname R2",
                "service password-encryption",
                "ipv6 unicast-routing",
                {"interface GigabitEthernet0/0/0": [
                    "ipv6 address 2001:DB8:ACAD:2::2/64",
                    "ipv6 address FE80::2 link-local"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "ipv6 address 2001:DB8:ACAD:3::1/64",
                    "ipv6 address FE80::2 link-local",
                    "ipv6 nd prefix 2001:DB8:ACAD:3::/64 2592000 604800 no-autoconfig",
                    "ipv6 nd managed-config-flag",
                    "ipv6 dhcp relay destination 2001:DB8:ACAD:2::1 GigabitEthernet0/0/0"
                ]},
                "ipv6 route ::/0 2001:DB8:ACAD:2::1"
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                "spanning-tree mode pvst"
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption", 
                "spanning-tree mode pvst"
            ]
            
            pc_a_config = {
                "ip": "2001:db8:acad:1::",
                "subnet": "64"
            }
            
            pc_b_config = {
                "ip": "2001:db8:acad:3::",
                "subnet": "64"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config
            }
            
        elif lab_num == 14:
            # คีย์เวิร์ดสำหรับ Lab 14 - Basic Static Route Configuration
            r1_keywords = [
                "hostname R1",
                "service password-encryption",
                "no ip domain-lookup",
                {"interface GigabitEthernet0/0/0": [
                    "ip address 209.165.200.230 255.255.255.248",
                    "duplex auto",
                    "speed auto"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "ip address 192.168.1.1 255.255.255.0",
                    "duplex auto",
                    "speed auto"
                ]},
                {"interface Loopback1": [
                    "ip address 209.165.200.1 255.255.255.224"
                ]},
                "ip route 0.0.0.0 0.0.0.0 209.165.200.225",
                {"line con 0": [
                    "password 7 0822455D0A16",
                    "login"
                ]},
                {"line vty 0 4": [
                    "password 7 0822455D0A16",
                    "login"
                ]}
            ]
            
            r2_keywords = [
                "hostname R2",
                "service password-encryption",
                "no ip domain-lookup",
                {"interface GigabitEthernet0/0/0": [
                    "ip address 209.165.200.225 255.255.255.248",
                    "duplex auto",
                    "speed auto"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "ip address 192.168.1.1 255.255.255.0",
                    "duplex auto",
                    "speed auto"
                ]},
                {"interface Loopback1": [
                    "ip address 209.165.200.1 255.255.255.224"
                ]},
                "ip route 0.0.0.0 0.0.0.0 209.165.200.225",
                {"line con 0": [
                    "password 7 0822455D0A16",
                    "login"
                ]},
                {"line vty 0 4": [
                    "password 7 0822455D0A16",
                    "login"
                ]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "service password-encryption",
                "no ip domain-lookup",
                "spanning-tree mode pvst",
                {"interface Vlan1": [
                    "ip address 192.168.1.11 255.255.255.0"
                ]},
                "ip default-gateway 192.168.1.1",
                {"line con 0": [
                    "password 7 0822455D0A16",
                    "login"
                ]},
                {"line vty 0 4": [
                    "password 7 0822455D0A16",
                    "login"
                ]}
            ]
            
            sw2_keywords = [
                "hostname S2",
                "service password-encryption", 
                "no ip domain-lookup",
                "spanning-tree mode pvst",
                {"interface Vlan1": [
                    "ip address 192.168.1.12 255.255.255.0"
                ]},
                "ip default-gateway 192.168.1.1",
                {"line con 0": [
                    "password 7 0822455D0A16",
                    "login"
                ]},
                {"line vty 0 4": [
                    "password 7 0822455D0A16",
                    "login"
                ]}
            ]
            
            pc_a_config = {
                "ip": "192.168.1.3",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.1"
            }
            
            pc_b_config = {
                "ip": "192.168.1.4",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.1"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_b_config": pc_b_config
            }
            
        elif lab_num == 15:
            # คีย์เวิร์ดสำหรับ Lab 15 - Configuring HSRP
            r1_keywords = [
                "hostname R1",
                "no ip domain lookup",
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.1.1 255.255.255.0",
                    "standby version 2",
                    "standby 1 ip 192.168.1.254",
                    "standby 1 priority 150",
                    "standby 1 preempt"
                ]},
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.1 255.255.255.252",
                    "clock rate 128000"
                ]},
                {"router rip": [
                    "network 10.1.1.0",
                    "network 192.168.1.0"
                ]}
            ]
            
            r2_keywords = [
                "hostname R2",
                "no ip domain lookup",
                {"interface Loopback1": [
                    "ip address 209.165.200.225 255.255.255.224"
                ]},
                {"interface Serial0/0/0": [
                    "ip address 10.1.1.2 255.255.255.252"
                ]},
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.2 255.255.255.252",
                    "clock rate 128000"
                ]},
                {"router rip": [
                    "network 10.1.1.0",
                    "network 10.2.2.0",
                    "default-information originate"
                ]},
                "ip route 0.0.0.0 0.0.0.0 Loopback1"
            ]
            
            r3_keywords = [
                "hostname R3",
                "no ip domain lookup",
                {"interface GigabitEthernet0/1": [
                    "ip address 192.168.1.3 255.255.255.0",
                    "standby version 2", 
                    "standby 1 ip 192.168.1.254",
                    "standby 1 priority 200",
                    "standby 1 preempt"
                ]},
                {"interface Serial0/0/1": [
                    "ip address 10.2.2.1 255.255.255.252"
                ]},
                {"router rip": [
                    "network 10.2.2.0",
                    "network 192.168.1.0"
                ]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface Vlan1": [
                    "ip address 192.168.1.11 255.255.255.0"
                ]},
                "ip default-gateway 192.168.1.254"
            ]
            
            sw2_keywords = [
                "hostname S3",
                "no ip domain-lookup",
                "spanning-tree mode pvst",
                {"interface Vlan1": [
                    "ip address 192.168.1.13 255.255.255.0"
                ]},
                "ip default-gateway 192.168.1.254"
            ]
            
            pc_a_config = {
                "ip": "192.168.1.31",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.254"
            }
            
            pc_c_config = {
                "ip": "192.168.1.33",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.254"
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_c_config": pc_c_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "r2_keywords": r2_keywords,
                "r3_keywords": r3_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "pc_a_config": pc_a_config,
                "pc_c_config": pc_c_config
            }
            
        elif lab_num == 16:
            # คีย์เวิร์ดสำหรับ Lab 16 - Switch Security Configuration
            r1_keywords = [
                "hostname R1",
                "no ip domain-lookup",
                {"interface Loopback0": [
                    "ip address 10.10.1.1 255.255.255.0"
                ]},
                {"interface GigabitEthernet0/0/1": [
                    "description Link to S1 Port 5",
                    "ip address 192.168.10.1 255.255.255.0"
                ]},
                "ip dhcp excluded-address 192.168.10.1 192.168.10.9",
                "ip dhcp excluded-address 192.168.10.201 192.168.10.202",
                {"ip dhcp pool Students": [
                    "network 192.168.10.0 255.255.255.0",
                    "default-router 192.168.10.1",
                    "domain-name CCNA2.Lab-11.6.1"
                ]}
            ]
            
            sw1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                "spanning-tree mode pvst",
                {"vlan 10": ["name Management"]},
                {"vlan 333": ["name Native"]},
                {"vlan 999": ["name ParkingLot"]},
                {"interface FastEthernet0/1": [
                    "description Link to S2",
                    "switchport trunk encapsulation dot1q",
                    "switchport trunk native vlan 333",
                    "switchport mode trunk",
                    "switchport nonegotiate"
                ]},
                {"interface FastEthernet0/5": [
                    "description Link to R1",
                    "switchport access vlan 10",
                    "switchport mode access",
                    "spanning-tree portfast"
                ]},
                {"interface FastEthernet0/6": [
                    "description Link to PC-A",
                    "switchport access vlan 10",
                    "switchport mode access",
                    "switchport port-security maximum 3",
                    "switchport port-security violation restrict",
                    "switchport port-security aging time 60",
                    "switchport port-security aging type inactivity",
                    "switchport port-security",
                    "spanning-tree portfast",
                    "spanning-tree bpduguard enable"
                ]},
                {"interface Vlan10": [
                    "description Management SVI",
                    "ip address 192.168.10.201 255.255.255.0"
                ]},
                "ip default-gateway 192.168.10.1"
            ]
            
            sw2_keywords = [
                "hostname S2",
                "no ip domain-lookup",
                "ip dhcp snooping vlan 10",
                "ip dhcp snooping",
                "spanning-tree mode pvst",
                {"vlan 10": ["name Students"]},
                {"vlan 333": ["name Native"]},
                {"vlan 999": ["name ParkingLot"]},
                {"interface FastEthernet0/1": [
                    "description Link to S1",
                    "switchport trunk native vlan 333",
                    "switchport mode trunk",
                    "switchport nonegotiate",
                    "ip dhcp snooping trust"
                ]},
                {"interface FastEthernet0/18": [
                    "description Link to PC-B",
                    "switchport access vlan 10",
                    "switchport mode access",
                    "switchport port-security maximum 2",
                    "switchport port-security violation protect",
                    "switchport port-security mac-address sticky",
                    "switchport port-security aging time 60",
                    "switchport port-security",
                    "spanning-tree portfast",
                    "spanning-tree bpduguard enable",
                    "ip dhcp snooping limit rate 5"
                ]},
                {"interface Vlan10": [
                    "description Management SVI",
                    "ip address 192.168.10.202 255.255.255.0"
                ]},
                "ip default-gateway 192.168.10.1"
            ]
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "r1_keywords": r1_keywords,
                "sw1_keywords": sw1_keywords,
                "sw2_keywords": sw2_keywords
            }
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

    # แปลงคีย์เวิร์ดเป็นข้อความเพื่อแสดงผล
    switch_keywords_text = ""
    switch1_keywords_text = ""
    switch2_keywords_text = ""
    general_keywords_text = ""
    r1_keywords_text = ""
    r2_keywords_text = ""
    r3_keywords_text = ""
    sw1_keywords_text = ""
    sw2_keywords_text = ""
    sw3_keywords_text = ""
    spanning_tree_sw1_text = ""
    spanning_tree_sw2_text = ""
    spanning_tree_sw3_text = ""

    # เพิ่มการตรวจสอบ
    pca_config = lab_keywords.get('pca_config', {}) if lab_keywords and 'pca_config' in lab_keywords else {}
    pcc_config = lab_keywords.get('pcc_config', {}) if lab_keywords and 'pcc_config' in lab_keywords else {}
    pcb_config = lab_keywords.get('pcb_config', {}) if lab_keywords and 'pcb_config' in lab_keywords else {}
    pc_config = lab_keywords.get('pc_config', {}) if lab_keywords and 'pc_config' in lab_keywords else {}
    pc1_config = lab_keywords.get('pc1_config', {}) if lab_keywords and 'pc1_config' in lab_keywords else {}
    pc2_config = lab_keywords.get('pc2_config', {}) if lab_keywords and 'pc2_config' in lab_keywords else {}
    pc_a_config = lab_keywords.get('pc_a_config', {}) if lab_keywords and 'pc_a_config' in lab_keywords else {}
    pc_c_config = lab_keywords.get('pc_c_config', {}) if lab_keywords and 'pc_c_config' in lab_keywords else {}
    pc_b_config = pcb_config

    if lab_num == 1:
        switch_keywords = lab_keywords.get('switch_keywords', [])
        switch_keywords_text = format_keywords_for_display(switch_keywords)
    elif lab_num == 2:
        switch1_keywords = lab_keywords.get('switch1_keywords', [])
        switch2_keywords = lab_keywords.get('switch2_keywords', [])
        switch1_keywords_text = format_keywords_for_display(switch1_keywords)
        switch2_keywords_text = format_keywords_for_display(switch2_keywords)
    elif lab_num == 3:
        # Lab 3 - Implement VLANs and Trunking
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 4:  # Lab 4 - Redundant Links
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        sw3_keywords = lab_keywords.get('sw3_keywords', [])
        spanning_tree_sw1 = lab_keywords.get('spanning_tree_sw1', {})
        spanning_tree_sw2 = lab_keywords.get('spanning_tree_sw2', {})
        spanning_tree_sw3 = lab_keywords.get('spanning_tree_sw3', {})
        
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        sw3_keywords_text = format_keywords_for_display(sw3_keywords)
        
        # แปลง spanning tree เป็นรูปแบบข้อความ
        spanning_tree_sw1_text = "\n".join([f"{port}: {status}" for port, status in spanning_tree_sw1.items()])
        spanning_tree_sw2_text = "\n".join([f"{port}: {status}" for port, status in spanning_tree_sw2.items()])
        spanning_tree_sw3_text = "\n".join([f"{port}: {status}" for port, status in spanning_tree_sw3.items()])
    elif lab_num == 5:  # Lab 5 - Rapid PVST+
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        sw3_keywords = lab_keywords.get('sw3_keywords', [])
        pca_config = lab_keywords.get('pca_config', {})
        pcc_config = lab_keywords.get('pcc_config', {})
        
        # กำหนดค่าเริ่มต้นถ้าไม่มีข้อมูล
        if not pca_config or 'ip' not in pca_config:
            pca_config = {"ip": "192.168.0.2", "subnet": "255.255.255.0"}
        
        if not pcc_config or 'ip' not in pcc_config:
            pcc_config = {"ip": "192.168.0.3", "subnet": "255.255.255.0"}
        
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        sw3_keywords_text = format_keywords_for_display(sw3_keywords)
    elif lab_num == 6:  # Lab 6 - Router-on-a-Stick Inter-VLAN
        r1_keywords = lab_keywords.get('r1_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 7:  # Lab 7 - Inter-VLAN Routing
        r1_keywords = lab_keywords.get('r1_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 8:  # Lab 8 - EtherChannel
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 9:  # Lab 9 - PPP Authentication
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        r3_keywords = lab_keywords.get('r3_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        r3_keywords_text = format_keywords_for_display(r3_keywords)
    elif lab_num == 10:  # Lab 10 - Standard IPv4 ACLs
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        r3_keywords = lab_keywords.get('r3_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw3_keywords = lab_keywords.get('sw3_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        r3_keywords_text = format_keywords_for_display(r3_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw3_keywords_text = format_keywords_for_display(sw3_keywords)
    elif lab_num == 11:  # Lab 11 - Extended IPv4 ACLs
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num >= 12 and lab_num <= 14:  # Lab 12-14
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 15:  # Lab 15 - HSRP
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        r3_keywords = lab_keywords.get('r3_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        r3_keywords_text = format_keywords_for_display(r3_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    elif lab_num == 16:  # Lab 16 - Switch Security Configuration
        r1_keywords = lab_keywords.get('r1_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
    else:
        # สำหรับแล็บอื่นๆ ที่ไม่ได้ระบุเฉพาะ
        general_keywords = lab_keywords.get('general_keywords', [])
        general_keywords_text = format_keywords_for_display(general_keywords)
        
        pc_b_config = pcb_config

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
                        switch_keywords_text=switch_keywords_text,
                        switch1_keywords_text=switch1_keywords_text,
                        switch2_keywords_text=switch2_keywords_text,
                        general_keywords_text=general_keywords_text,
                        r1_keywords_text=r1_keywords_text,
                        r2_keywords_text=r2_keywords_text,
                        r3_keywords_text=r3_keywords_text,
                        sw1_keywords_text=sw1_keywords_text,
                        sw2_keywords_text=sw2_keywords_text,
                        sw3_keywords_text=sw3_keywords_text,
                        spanning_tree_sw1_text=spanning_tree_sw1_text,
                        spanning_tree_sw2_text=spanning_tree_sw2_text,
                        spanning_tree_sw3_text=spanning_tree_sw3_text,
                        pc_config=pc_config,
                        pc1_config=pc1_config,
                        pc2_config=pc2_config,
                        pc_a_config=pc_a_config,
                        pc_b_config=pcb_config,
                        pc_c_config=pc_c_config,
                        active_lab=lab_num,
                        first_name=first_name,
                        last_name=last_name)# ดูรายละเอียดการส่งงานของนักศึกษา
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
        elif lab_num == 3:
            # อัพเดทสำหรับ Lab 3
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            pc1_ip = request.form.get('pc1_ip', '')
            pc1_subnet = request.form.get('pc1_subnet', '')
            pc1_gateway = request.form.get('pc1_gateway', '')
            pc2_ip = request.form.get('pc2_ip', '')
            pc2_subnet = request.form.get('pc2_subnet', '')
            pc2_gateway = request.form.get('pc2_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
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
            
        elif lab_num == 4:
            # อัพเดทสำหรับ Lab 4
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            sw3_keywords_text = request.form.get('sw3_keywords', '')
            spanning_tree_sw1_text = request.form.get('spanning_tree_sw1', '')
            spanning_tree_sw2_text = request.form.get('spanning_tree_sw2', '')
            spanning_tree_sw3_text = request.form.get('spanning_tree_sw3', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            sw3_keywords = parse_keywords_from_text(sw3_keywords_text)
            
            # แปลงข้อความเป็น dict ของสถานะ spanning tree
            spanning_tree_sw1 = {}
            spanning_tree_sw2 = {}
            spanning_tree_sw3 = {}
            
            for line in spanning_tree_sw1_text.strip().split('\n'):
                if line.strip() and ':' in line:
                    port, status = line.split(':', 1)
                    spanning_tree_sw1[port.strip()] = status.strip()
                    
            for line in spanning_tree_sw2_text.strip().split('\n'):
                if line.strip() and ':' in line:
                    port, status = line.split(':', 1)
                    spanning_tree_sw2[port.strip()] = status.strip()
                    
            for line in spanning_tree_sw3_text.strip().split('\n'):
                if line.strip() and ':' in line:
                    port, status = line.split(':', 1)
                    spanning_tree_sw3[port.strip()] = status.strip()
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "sw3_keywords": sw3_keywords,
                    "spanning_tree_sw1": spanning_tree_sw1,
                    "spanning_tree_sw2": spanning_tree_sw2,
                    "spanning_tree_sw3": spanning_tree_sw3,
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
        elif lab_num == 5:
            # ดึงข้อมูลจากฟอร์ม
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            sw3_keywords_text = request.form.get('sw3_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pcc_ip = request.form.get('pcc_ip', '')
            pcc_subnet = request.form.get('pcc_subnet', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            sw3_keywords = parse_keywords_from_text(sw3_keywords_text)
            
            # สร้าง config ในรูปแบบที่เข้าถึงด้วย .ip และ .subnet ได้
            pca_config = {
                "ip": pca_ip,
                "subnet": pca_subnet
            }
            
            pcc_config = {
                "ip": pcc_ip,
                "subnet": pcc_subnet
            }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "sw3_keywords": sw3_keywords,
                    "pca_config": pca_config,
                    "pcc_config": pcc_config,
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
            
        elif lab_num == 6:
            # อัพเดทสำหรับ Lab 6
            r1_keywords_text = request.form.get('r1_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            pcb_ip = request.form.get('pcb_ip', '')
            pcb_subnet = request.form.get('pcb_subnet', '')
            pcb_gateway = request.form.get('pcb_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
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
        # เพิ่มเงื่อนไขสำหรับ Lab 7
        elif lab_num == 7:
            r1_keywords_text = request.form.get('r1_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            pcb_ip = request.form.get('pcb_ip', '')
            pcb_subnet = request.form.get('pcb_subnet', '')
            pcb_gateway = request.form.get('pcb_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
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
        # เพิ่มเงื่อนไขสำหรับ Lab 8
        elif lab_num == 8:
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pcb_ip = request.form.get('pcb_ip', '')
            pcb_subnet = request.form.get('pcb_subnet', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "pca_config": {
                        "ip": pca_ip,
                        "subnet": pca_subnet
                    },
                    "pcb_config": {
                        "ip": pcb_ip,
                        "subnet": pcb_subnet
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        # เพิ่มเงื่อนไขสำหรับ Lab 9
        elif lab_num == 9:
            r1_keywords_text = request.form.get('r1_keywords', '')
            r2_keywords_text = request.form.get('r2_keywords', '')
            r3_keywords_text = request.form.get('r3_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            pcc_ip = request.form.get('pcc_ip', '')
            pcc_subnet = request.form.get('pcc_subnet', '')
            pcc_gateway = request.form.get('pcc_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            r2_keywords = parse_keywords_from_text(r2_keywords_text)
            r3_keywords = parse_keywords_from_text(r3_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "r2_keywords": r2_keywords,
                    "r3_keywords": r3_keywords,
                    "pca_config": {
                        "ip": pca_ip,
                        "subnet": pca_subnet,
                        "gateway": pca_gateway
                    },
                    "pcc_config": {
                        "ip": pcc_ip,
                        "subnet": pcc_subnet,
                        "gateway": pcc_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        # เพิ่มเงื่อนไขสำหรับ Lab 10
        elif lab_num == 10:
            r1_keywords_text = request.form.get('r1_keywords', '')
            r2_keywords_text = request.form.get('r2_keywords', '')
            r3_keywords_text = request.form.get('r3_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw3_keywords_text = request.form.get('sw3_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            pcc_ip = request.form.get('pcc_ip', '')
            pcc_subnet = request.form.get('pcc_subnet', '')
            pcc_gateway = request.form.get('pcc_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            r2_keywords = parse_keywords_from_text(r2_keywords_text)
            r3_keywords = parse_keywords_from_text(r3_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw3_keywords = parse_keywords_from_text(sw3_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "r2_keywords": r2_keywords,
                    "r3_keywords": r3_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw3_keywords": sw3_keywords,
                    "pca_config": {
                        "ip": pca_ip,
                        "subnet": pca_subnet,
                        "gateway": pca_gateway
                    },
                    "pcc_config": {
                        "ip": pcc_ip,
                        "subnet": pcc_subnet,
                        "gateway": pcc_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        # เพิ่มเงื่อนไขสำหรับ Lab 11
        elif lab_num == 11:
            r1_keywords_text = request.form.get('r1_keywords', '')
            r2_keywords_text = request.form.get('r2_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pca_gateway = request.form.get('pca_gateway', '')
            pcb_ip = request.form.get('pcb_ip', '')
            pcb_subnet = request.form.get('pcb_subnet', '')
            pcb_gateway = request.form.get('pcb_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            r2_keywords = parse_keywords_from_text(r2_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "r2_keywords": r2_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
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
        # เพิ่มเงื่อนไขเพิ่มเติมในฟังก์ชัน update_keywords
       # เพิ่มเงื่อนไขเพิ่มเติมในฟังก์ชัน update_keywords
        elif lab_num == 12 or lab_num == 13 or lab_num == 14:
            r1_keywords_text = request.form.get('r1_keywords', '')
            r2_keywords_text = request.form.get('r2_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            
            pc_a_ip = request.form.get('pc_a_ip', '')
            pc_a_subnet = request.form.get('pc_a_subnet', '')
            pc_a_gateway = request.form.get('pc_a_gateway', '')
            
            pc_b_ip = request.form.get('pc_b_ip', '')
            pc_b_subnet = request.form.get('pc_b_subnet', '')
            pc_b_gateway = request.form.get('pc_b_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            r2_keywords = parse_keywords_from_text(r2_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "r2_keywords": r2_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "pc_a_config": {
                        "ip": pc_a_ip,
                        "subnet": pc_a_subnet,
                        "gateway": pc_a_gateway
                    },
                    "pc_b_config": {
                        "ip": pc_b_ip,
                        "subnet": pc_b_subnet,
                        "gateway": pc_b_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )

        elif lab_num == 15:
            r1_keywords_text = request.form.get('r1_keywords', '')
            r2_keywords_text = request.form.get('r2_keywords', '')
            r3_keywords_text = request.form.get('r3_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            
            pc_a_ip = request.form.get('pc_a_ip', '')
            pc_a_subnet = request.form.get('pc_a_subnet', '')
            pc_a_gateway = request.form.get('pc_a_gateway', '')
            
            pc_c_ip = request.form.get('pc_c_ip', '')
            pc_c_subnet = request.form.get('pc_c_subnet', '')
            pc_c_gateway = request.form.get('pc_c_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            r2_keywords = parse_keywords_from_text(r2_keywords_text)
            r3_keywords = parse_keywords_from_text(r3_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "r2_keywords": r2_keywords,
                    "r3_keywords": r3_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "pc_a_config": {
                        "ip": pc_a_ip,
                        "subnet": pc_a_subnet,
                        "gateway": pc_a_gateway
                    },
                    "pc_c_config": {
                        "ip": pc_c_ip,
                        "subnet": pc_c_subnet,
                        "gateway": pc_c_gateway
                    },
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )

        elif lab_num == 16:
            r1_keywords_text = request.form.get('r1_keywords', '')
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            r1_keywords = parse_keywords_from_text(r1_keywords_text)
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "r1_keywords": r1_keywords,
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
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
    keywords = []
    lines = text.strip().split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith('interface'):
            interface_name = line
            interface_commands = []
            i += 1
            
            # เก็บคำสั่งภายใน interface จนกว่าจะเจอ interface ถัดไปหรือจบไฟล์
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('interface'):
                cmd = lines[i].strip()
                if cmd:  # ไม่เพิ่มบรรทัดว่าง
                    interface_commands.append(cmd)
                i += 1
                
            # เพิ่ม interface พร้อมคำสั่งย่อย
            if interface_commands:
                keywords.append({interface_name: interface_commands})
        else:
            # คำสั่งทั่วไป
            keywords.append(line)
            i += 1
    
    return keywords