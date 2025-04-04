from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime , timedelta
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
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
    completion_rate = min((completed_students / total_students) * 100, 100) if total_students > 0 else 0
    
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
        student['completion_rate'] = min((completed_labs / 16) * 100, 100) if completed_labs > 0 else 0
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # คำนวณเวลาส่งงานล่าสุด
    latest_submission = max([score.get('timestamp', datetime.min).replace(microsecond=0) for score in all_scores], default=None)
    
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
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
                'completion_rate': min(sum([1 for s in lab_scores if float(s['switch_score'].split('/')[0]) >= 60]) / len(lab_scores) * 100, 100) if lab_scores else 0
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
    completion_rate = min((completed_students / total_students) * 100, 100) if total_students > 0 else 0
    
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
                          completion_rate=completion_rate,
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
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
    expected_vlans_sw1 = {}  # เพิ่มตรงนี้
    expected_vlans_sw2 = {}  # เพิ่มตรงนี้
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            })
            
            lab_keywords = {
                "general_keywords": default_keywords
            }

        # ดึงข้อมูลการส่งแล็บของนักศึกษาทั้งหมด
    submissions = list(scores_collection.find({"lab": f"Lab {lab_num}"}))
    
    # แก้ไขส่วนที่สร้าง students_data
    students_data = []
    processed_usernames = set()  # เก็บ usernames ที่ประมวลผลแล้วเพื่อป้องกันการซ้ำ

    for submission in submissions:
        username = submission['username']
        
        # ตรวจสอบว่าเคยประมวลผลนักศึกษาคนนี้แล้วหรือไม่
        if username not in processed_usernames:
            processed_usernames.add(username)
            student = students_collection.find_one({"username": username})
            
            if student:
                try:
                    score = float(submission['switch_score'].split('/')[0])
                    status = 'completed' if score >= 60 else 'in_progress'
                    status_text = 'เสร็จสมบูรณ์' if score >= 60 else 'ยังไม่สมบูรณ์'
                except Exception:
                    score = 0
                    status = 'in_progress'
                    status_text = 'ยังไม่สมบูรณ์'
                
                students_data.append({
                    'student_id': username,
                    'name': f"{student.get('first_name', '')} {student.get('last_name', '')}",
                    'score': score,
                    'status': status,
                    'status_text': status_text,
                    'timestamp': submission.get('timestamp', 'Unknown').replace(microsecond=0)
                })

    # นับจำนวนนักศึกษาที่ไม่ซ้ำกัน
    unique_students_count = len(processed_usernames)
    # เรียงลำดับตามคะแนน (มากไปน้อย) - ตรงนี้ที่เกิด error
    if students_data:  # ตรวจสอบว่ามีข้อมูลก่อนเรียง
        students_data.sort(key=lambda x: x['score'], reverse=True)
    # เรียงลำดับตามคะแนน (มากไปน้อย)
    
    # คำนวณข้อมูลสถิติ
    total_students = students_collection.count_documents({})
    completed_count = sum(1 for student in students_data if student['status'] == 'completed')
    completion_rate = min((completed_count / total_students) * 100, 100) if total_students > 0 else 0
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
        expected_vlans_sw1 = lab_keywords.get('expected_vlans_sw1', {}) if lab_keywords else {}
        expected_vlans_sw2 = lab_keywords.get('expected_vlans_sw2', {}) if lab_keywords else {}
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
        
        # ตรวจสอบและแปลง pca_config และ pcb_config เพื่อใช้กับ template
        pca_config = lab_keywords.get('pca_config', {})
        pcb_config = lab_keywords.get('pcb_config', {})
    
    # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pcb_config or not isinstance(pcb_config, dict):
            pcb_config = {"ip": "", "subnet": "", "gateway": ""}
        
    # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_b_config = pcb_config
    elif lab_num == 7:  # Lab 7 - Inter-VLAN Routing
        r1_keywords = lab_keywords.get('r1_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        
        # ตรวจสอบและแปลง pca_config และ pcb_config
        pca_config = lab_keywords.get('pca_config', {})
        pcb_config = lab_keywords.get('pcb_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pcb_config or not isinstance(pcb_config, dict):
            pcb_config = {"ip": "", "subnet": "", "gateway": ""}
        
        # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_b_config = pcb_config

    elif lab_num == 8:  # Lab 8 - EtherChannel
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        
        # ตรวจสอบและแปลง pca_config และ pcb_config
        pca_config = lab_keywords.get('pca_config', {})
        pcb_config = lab_keywords.get('pcb_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": ""}
        if not pcb_config or not isinstance(pcb_config, dict):
            pcb_config = {"ip": "", "subnet": ""}
        
        # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_b_config = pcb_config

    elif lab_num == 9:  # Lab 9 - PPP Authentication
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        r3_keywords = lab_keywords.get('r3_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        r3_keywords_text = format_keywords_for_display(r3_keywords)
        
        # ตรวจสอบและแปลง pca_config และ pcc_config
        pca_config = lab_keywords.get('pca_config', {})
        pcc_config = lab_keywords.get('pcc_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pcc_config or not isinstance(pcc_config, dict):
            pcc_config = {"ip": "", "subnet": "", "gateway": ""}
        
        # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_c_config = pcc_config

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
        
        # ตรวจสอบและแปลง pca_config และ pcc_config
        pca_config = lab_keywords.get('pca_config', {})
        pcc_config = lab_keywords.get('pcc_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pcc_config or not isinstance(pcc_config, dict):
            pcc_config = {"ip": "", "subnet": "", "gateway": ""}
        
        # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_c_config = pcc_config

    elif lab_num == 11:  # Lab 11 - Extended IPv4 ACLs
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        
        # ตรวจสอบและแปลง pca_config และ pcb_config
        pca_config = lab_keywords.get('pca_config', {})
        pcb_config = lab_keywords.get('pcb_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pca_config or not isinstance(pca_config, dict):
            pca_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pcb_config or not isinstance(pcb_config, dict):
            pcb_config = {"ip": "", "subnet": "", "gateway": ""}
        
        # กำหนดค่าให้ตัวแปรที่ template ต้องการ
        pc_a_config = pca_config
        pc_b_config = pcb_config

    elif lab_num >= 12 and lab_num <= 14:  # Lab 12-14
        r1_keywords = lab_keywords.get('r1_keywords', [])
        r2_keywords = lab_keywords.get('r2_keywords', [])
        sw1_keywords = lab_keywords.get('sw1_keywords', [])
        sw2_keywords = lab_keywords.get('sw2_keywords', [])
        
        r1_keywords_text = format_keywords_for_display(r1_keywords)
        r2_keywords_text = format_keywords_for_display(r2_keywords)
        sw1_keywords_text = format_keywords_for_display(sw1_keywords)
        sw2_keywords_text = format_keywords_for_display(sw2_keywords)
        
        # ตรวจสอบและแปลง pc_a_config และ pc_b_config
        pc_a_config = lab_keywords.get('pc_a_config', {})
        pc_b_config = lab_keywords.get('pc_b_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pc_a_config or not isinstance(pc_a_config, dict):
            pc_a_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pc_b_config or not isinstance(pc_b_config, dict):
            pc_b_config = {"ip": "", "subnet": "", "gateway": ""}

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
        
        # ตรวจสอบและแปลง pc_a_config และ pc_c_config
        pc_a_config = lab_keywords.get('pc_a_config', {})
        pc_c_config = lab_keywords.get('pc_c_config', {})
        
        # ตรวจสอบว่ามีข้อมูลหรือไม่ และกำหนดค่า default ถ้าไม่มี
        if not pc_a_config or not isinstance(pc_a_config, dict):
            pc_a_config = {"ip": "", "subnet": "", "gateway": ""}
        if not pc_c_config or not isinstance(pc_c_config, dict):
            pc_c_config = {"ip": "", "subnet": "", "gateway": ""}
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
                        pc_b_config=pc_b_config,
                        pc_c_config=pc_c_config,
                        expected_vlans_sw1=expected_vlans_sw1,  # เพิ่มบรรทัดนี้
                        expected_vlans_sw2=expected_vlans_sw2,  # เพิ่มบรรทัดนี้
                        active_lab=lab_num,
                        first_name=first_name,
                        last_name=last_name)
def format_vlans_for_display(vlans):
    """
    แปลง dict ของ VLANs เป็นข้อความที่อ่านง่าย
    """
    if not vlans:
        return "ไม่มีข้อมูล VLAN"
    
    vlan_text = ""
    for vlan_id, vlan_info in vlans.items():
        vlan_text += f"VLAN {vlan_id}:\n"
        vlan_text += f"  Name: {vlan_info.get('name', 'N/A')}\n"
        
        ports = vlan_info.get('ports', [])
        if ports:
            vlan_text += f"  Ports: {', '.join(ports)}\n"
        
        vlan_text += "\n"
    
    return vlan_text.strip()


@teacher_bp.route('/submission/<int:lab_num>/<student_id>')
def view_submission(lab_num, student_id):
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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

    # ดึงข้อมูลการส่งงานทั้งหมดของนักศึกษา
    submission_history_raw = list(scores_collection.find({
    "username": student_id, 
    "lab": f"Lab {lab_num}"
    }).sort("timestamp", -1))

    submission_history = []
    for record in submission_history_raw:
        # ตรวจสอบว่า timestamp เป็นออบเจ็กต์ datetime หรือไม่
        if isinstance(record.get('timestamp'), datetime):
            # ถ้าเป็น datetime ให้จัดรูปแบบ
            record['timestamp'] = record['timestamp'].replace(microsecond=0)
        submission_history.append(record)
        
    # นับจำนวนครั้งที่ส่งงาน
    submission_count = len(submission_history)

    # เพิ่มข้อมูลจำนวนครั้งที่ส่งเข้าไปใน submission
    submission['submission_count'] = submission_count

    # เพิ่มเก็บข้อมูลประวัติย่อนหลังเข้าไปด้วย
    submission['history'] = submission_history

    # เตรียมข้อมูล PC configs สำหรับทุก Lab
    pc_config = {"ip_address": "", "subnet_mask": "", "default_gateway": ""}
    pc1_config = {"ip": "", "subnet": "", "gateway": ""}
    pc2_config = {"ip": "", "subnet": "", "gateway": ""}
    pca_config = {"ip": "", "subnet": "", "gateway": ""}
    pcb_config = {"ip": "", "subnet": "", "gateway": ""}
    pcc_config = {"ip": "", "subnet": "", "gateway": ""}
    pc_a_config = {"ip": "", "subnet": "", "gateway": ""}
    pc_b_config = {"ip": "", "subnet": "", "gateway": ""}
    pc_c_config = {"ip": "", "subnet": "", "gateway": ""}
    
    # เตรียมข้อมูลอุปกรณ์ต่างๆ สำหรับแต่ละ Lab
    # เก็บชื่ออุปกรณ์ที่ใช้ในแต่ละ Lab เพื่อส่งไปยัง template
    lab_devices = {
        # สำหรับแต่ละ lab จะกำหนดว่ามีอุปกรณ์อะไรบ้าง
        # ทั้ง "switches", "routers", "pcs" และอื่นๆ
    }
    
    # กำหนดชื่อแล็บตามหมายเลข
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
        14: "Static Route Configuration",
        15: "HSRP",
        16: "Switch Security Configuration"
    }
    
    # จัดการข้อมูลตามแต่ละ Lab
    if lab_num == 1:
        # Lab 1 - Basic Switch Configuration
        lab_devices = {
            "switches": ["S1"],
            "pcs": ["PC-A"]
        }
        
        if 'switch_config' not in submission or not submission['switch_config']:
            submission['switch_config'] = 'ไม่มีข้อมูล'
            
        if 'pc_config' in submission and isinstance(submission['pc_config'], dict):
            pc_config = submission['pc_config']
        else:
            # ใช้ค่าแยกถ้าไม่มี pc_config
            pc_config = {
                "ip_address": submission.get('pc_ip_address', ''),
                "subnet_mask": submission.get('pc_subnet_mask', ''),
                "default_gateway": submission.get('pc_default_gateway', '')
            }
    
    elif lab_num == 2:
        # Lab 2 - Configure VLANs and Trunking
        lab_devices = {
            "switches": ["S1", "S2"],
            "pcs": ["PC1", "PC2"]
        }
        
        if 'configs' in submission and isinstance(submission['configs'], dict):
            # ตรวจสอบว่ามีข้อมูล Switch config หรือไม่
            if 'sw1_config' not in submission['configs'] or not submission['configs']['sw1_config']:
                submission['configs']['sw1_config'] = 'ไม่มีข้อมูล'
            if 'sw2_config' not in submission['configs'] or not submission['configs']['sw2_config']:
                submission['configs']['sw2_config'] = 'ไม่มีข้อมูล'
        else:
            # สร้าง configs object ถ้าไม่มี
            submission['configs'] = {
                'sw1_config': 'ไม่มีข้อมูล',
                'sw2_config': 'ไม่มีข้อมูล'
            }
        
        # ตรวจสอบข้อมูล PC config
        if 'pc1_config' in submission and isinstance(submission['pc1_config'], dict):
            pc1_config = submission['pc1_config']
        else:
            pc1_config = {"ip": "192.168.10.3", "subnet": "255.255.255.0", "gateway": "192.168.10.1"}
            
        if 'pc2_config' in submission and isinstance(submission['pc2_config'], dict):
            pc2_config = submission['pc2_config']
        else:
            pc2_config = {"ip": "192.168.10.4", "subnet": "255.255.255.0", "gateway": "192.168.10.1"}
    
    elif lab_num == 3:
        # Lab 3 - Implement VLANs and Trunking
        lab_devices = {
            "switches": ["S1", "S2"],
            "pcs": ["PC1", "PC2"],
            "features": ["VLANs"]
        }
        
        # การจัดการข้อมูล Switch config
        if 'sw1_config' in submission:
            submission['switch1_config'] = submission['sw1_config']
        elif 'configs' in submission and isinstance(submission['configs'], dict) and 'sw1_config' in submission['configs']:
            submission['switch1_config'] = submission['configs']['sw1_config']
        else:
            submission['switch1_config'] = 'ไม่มีข้อมูล'
            
        if 'sw2_config' in submission:
            submission['switch2_config'] = submission['sw2_config']
        elif 'configs' in submission and isinstance(submission['configs'], dict) and 'sw2_config' in submission['configs']:
            submission['switch2_config'] = submission['configs']['sw2_config']
        else:
            submission['switch2_config'] = 'ไม่มีข้อมูล'
        
        # ดึงข้อมูล VLAN config
        submission['vlan_sw1_config'] = submission.get('vlan_sw1_config', '')
        submission['vlan_sw2_config'] = submission.get('vlan_sw2_config', '')
        
        # หากไม่มีข้อมูล VLAN ให้ใช้ข้อมูลจาก lab_keywords
        if not submission['vlan_sw1_config']:
            lab_keywords = lab_keywords_collection.find_one({"lab_num": lab_num})
            if lab_keywords and 'expected_vlans_sw1' in lab_keywords:
                expected_vlans_sw1 = lab_keywords['expected_vlans_sw1']
                submission['vlan_sw1_config'] = format_vlans_for_display(expected_vlans_sw1)
        
        if not submission['vlan_sw2_config']:
            lab_keywords = lab_keywords_collection.find_one({"lab_num": lab_num})
            if lab_keywords and 'expected_vlans_sw2' in lab_keywords:
                expected_vlans_sw2 = lab_keywords['expected_vlans_sw2']
                submission['vlan_sw2_config'] = format_vlans_for_display(expected_vlans_sw2)
        
        # ดึงข้อมูล PC1 config
        if 'pc1_config' in submission and isinstance(submission['pc1_config'], dict):
            if 'ip' in submission['pc1_config']:
                pc1_config = {
                    "ip": submission['pc1_config'].get('ip', ''),
                    "subnet": submission['pc1_config'].get('subnet', ''),
                    "gateway": submission['pc1_config'].get('gateway', '')
                }
            else:
                pc1_config = {"ip": "", "subnet": "", "gateway": ""}
                for key, value in submission['pc1_config'].items():
                    if 'ip' in key.lower():
                        pc1_config['ip'] = value
                    elif 'subnet' in key.lower() or 'mask' in key.lower():
                        pc1_config['subnet'] = value
                    elif 'gateway' in key.lower():
                        pc1_config['gateway'] = value
                        
            submission['pc1_ip_address'] = pc1_config['ip']
            submission['pc1_subnet_mask'] = pc1_config['subnet']
            submission['pc1_default_gateway'] = pc1_config['gateway']
        else:
            pc1_config = {
                "ip": submission.get('pc1_ip_address', '192.168.20.3'),
                "subnet": submission.get('pc1_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pc1_default_gateway', '192.168.20.1')
            }
            submission['pc1_ip_address'] = pc1_config['ip']
            submission['pc1_subnet_mask'] = pc1_config['subnet']
            submission['pc1_default_gateway'] = pc1_config['gateway']
        
        # ดึงข้อมูล PC2 config
        if 'pc2_config' in submission and isinstance(submission['pc2_config'], dict):
            if 'ip' in submission['pc2_config']:
                pc2_config = {
                    "ip": submission['pc2_config'].get('ip', ''),
                    "subnet": submission['pc2_config'].get('subnet', ''),
                    "gateway": submission['pc2_config'].get('gateway', '')
                }
            else:
                pc2_config = {"ip": "", "subnet": "", "gateway": ""}
                for key, value in submission['pc2_config'].items():
                    if 'ip' in key.lower():
                        pc2_config['ip'] = value
                    elif 'subnet' in key.lower() or 'mask' in key.lower():
                        pc2_config['subnet'] = value
                    elif 'gateway' in key.lower():
                        pc2_config['gateway'] = value
                        
            submission['pc2_ip_address'] = pc2_config['ip']
            submission['pc2_subnet_mask'] = pc2_config['subnet']
            submission['pc2_default_gateway'] = pc2_config['gateway']
        else:
            pc2_config = {
                "ip": submission.get('pc2_ip_address', '192.168.30.3'),
                "subnet": submission.get('pc2_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pc2_default_gateway', '192.168.30.1')
            }
            submission['pc2_ip_address'] = pc2_config['ip']
            submission['pc2_subnet_mask'] = pc2_config['subnet']
            submission['pc2_default_gateway'] = pc2_config['gateway']
            
    elif lab_num == 4:
        # Lab 4 - Redundant Links
        lab_devices = {
            "switches": ["S1", "S2", "S3"],
            "features": ["Spanning Tree"]
        }
        
        # การจัดการข้อมูล Switch config
        print("Debug - Original submission:", submission)  # เพิ่มบรรทัดนี้เพื่อดู submission ต้นฉบับ
        
        # สำหรับ Switch 1
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'sw1_config' in submission['configs']:
            submission['switch1_config'] = submission['configs']['sw1_config']
        elif 'sw1_config' in submission:
            submission['switch1_config'] = submission['sw1_config']
        else:
            submission['switch1_config'] = submission.get('switch_config', 'ไม่มีข้อมูล')
        
        # สำหรับ Switch 2
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'sw2_config' in submission['configs']:
            submission['switch2_config'] = submission['configs']['sw2_config']
        elif 'sw2_config' in submission:
            submission['switch2_config'] = submission['sw2_config']
        else:
            submission['switch2_config'] = 'ไม่มีข้อมูล'
        
        # สำหรับ Switch 3
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'sw3_config' in submission['configs']:
            submission['switch3_config'] = submission['configs']['sw3_config']
        elif 'sw3_config' in submission:
            submission['switch3_config'] = submission['sw3_config']
        else:
            submission['switch3_config'] = 'ไม่มีข้อมูล'
        
        print("Debug - After setting configs:", {
            'switch1_config': submission.get('switch1_config', 'not set'),
            'switch2_config': submission.get('switch2_config', 'not set'),
            'switch3_config': submission.get('switch3_config', 'not set')
        })  # เพิ่มบรรทัดนี้เพื่อตรวจสอบ
        
        # ดึงข้อมูล Spanning Tree
        if 'configs' in submission and isinstance(submission['configs'], dict):
            # ตรวจสอบ key ที่อาจเป็นไปได้ทั้งหมด
            possible_keys = [
                'spanning_sw1', 'spanning_tree_sw1', 'spanning-sw1', 'spanning_tree_s1',
                'spanning_sw1_config', 'spanning_tree_switch1'
            ]
            
            # ค้นหา key ที่มีอยู่ใน configs
            for key in possible_keys:
                if key in submission['configs']:
                    submission['spanning_sw1'] = submission['configs'][key]
                    break
            else:
                submission['spanning_sw1'] = 'ไม่มีข้อมูล'
            
            # ทำเช่นเดียวกันสำหรับ Switch 2
            possible_keys = [
                'spanning_sw2', 'spanning_tree_sw2', 'spanning-sw2', 'spanning_tree_s2',
                'spanning_sw2_config', 'spanning_tree_switch2'
            ]
            
            for key in possible_keys:
                if key in submission['configs']:
                    submission['spanning_sw2'] = submission['configs'][key]
                    break
            else:
                submission['spanning_sw2'] = 'ไม่มีข้อมูล'
                
            # ทำเช่นเดียวกันสำหรับ Switch 3
            possible_keys = [
                'spanning_sw3', 'spanning_tree_sw3', 'spanning-sw3', 'spanning_tree_s3',
                'spanning_sw3_config', 'spanning_tree_switch3'
            ]
            
            for key in possible_keys:
                if key in submission['configs']:
                    submission['spanning_sw3'] = submission['configs'][key]
                    break
            else:
                submission['spanning_sw3'] = 'ไม่มีข้อมูล'
                
        # ตรวจสอบสำหรับชื่อฟิลด์อื่นๆ ที่อาจเป็นไปได้
        if 'spanning_sw1' not in submission:
            submission['spanning_sw1'] = (
                submission.get('spanning_tree_sw1') or 
                submission.get('spanning-sw1') or 
                submission.get('spanning_tree_s1') or 
                'ไม่มีข้อมูล'
            )
        
        if 'spanning_sw2' not in submission:
            submission['spanning_sw2'] = (
                submission.get('spanning_tree_sw2') or 
                submission.get('spanning-sw2') or 
                submission.get('spanning_tree_s2') or 
                'ไม่มีข้อมูล'
            )
            
        if 'spanning_sw3' not in submission:
            submission['spanning_sw3'] = (
                submission.get('spanning_tree_sw3') or 
                submission.get('spanning-sw3') or 
                submission.get('spanning_tree_s3') or 
                'ไม่มีข้อมูล'
            )
            
        # กำหนดค่า Spanning Tree Mode และข้อมูลอื่นๆ
        if 'spanning_tree_mode' not in submission:
            if 'configs' in submission and isinstance(submission['configs'], dict) and 'spanning_tree_mode' in submission['configs']:
                submission['spanning_tree_mode'] = submission['configs']['spanning_tree_mode']
            else:
                submission['spanning_tree_mode'] = 'PVST+'
        
        # ตรวจสอบ root_bridge
        if 'root_bridge' not in submission:
            if 'configs' in submission and isinstance(submission['configs'], dict) and 'root_bridge' in submission['configs']:
                submission['root_bridge'] = submission['configs']['root_bridge']
            else:
                submission['root_bridge'] = 'ไม่มีข้อมูล'
        
        # ตรวจสอบ port_states
        if 'port_states' not in submission:
            if 'configs' in submission and isinstance(submission['configs'], dict) and 'port_states' in submission['configs']:
                submission['port_states'] = submission['configs']['port_states']
            else:
                submission['port_states'] = 'ไม่มีข้อมูล'
    elif lab_num == 5:
        # Lab 5 - Rapid PVST+
        lab_devices = {
            "switches": ["S1", "S2", "S3"],
            "pcs": ["PC-A", "PC-C"],
            "features": ["RPVST+"]
        }
        
        # การจัดการข้อมูล Switch config
        if 'configs' in submission and isinstance(submission['configs'], dict):
            # ข้อมูลอยู่ใน configs object
            if 'sw1_config' in submission['configs']:
                submission['switch1_config'] = submission['configs']['sw1_config']
            else:
                submission['switch1_config'] = 'ไม่มีข้อมูล'
                
            if 'sw2_config' in submission['configs']:
                submission['switch2_config'] = submission['configs']['sw2_config']
            else:
                submission['switch2_config'] = 'ไม่มีข้อมูล'
                
            if 'sw3_config' in submission['configs']:
                submission['switch3_config'] = submission['configs']['sw3_config']
            else:
                submission['switch3_config'] = 'ไม่มีข้อมูล'
        else:
            # ถ้าไม่มี configs object ลองดูว่ามี switch config ตรงๆ ไหม
            submission['switch1_config'] = submission.get('sw1_config', submission.get('switch_config', 'ไม่มีข้อมูล'))
            submission['switch2_config'] = submission.get('sw2_config', 'ไม่มีข้อมูล')
            submission['switch3_config'] = submission.get('sw3_config', 'ไม่มีข้อมูล')
        
        # PC Config สำหรับ PC-A
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pca_config' in submission['configs']:
            pca_config = submission['configs']['pca_config']
            if isinstance(pca_config, dict):
                submission['pca_ip_address'] = pca_config.get('ip', '')
                submission['pca_subnet_mask'] = pca_config.get('subnet', '')
        elif 'pca_config' in submission and isinstance(submission['pca_config'], dict):
            submission['pca_ip_address'] = submission['pca_config'].get('ip', '')
            submission['pca_subnet_mask'] = submission['pca_config'].get('subnet', '')
        else:
            # ถ้าไม่มีข้อมูลเฉพาะเจาะจงของ PC-A ลองดึงจากข้อมูลทั่วไป
            submission['pca_ip_address'] = submission.get('pc_ip_address', '')
            submission['pca_subnet_mask'] = submission.get('pc_subnet_mask', '')
        
        # PC Config สำหรับ PC-C
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pcc_config' in submission['configs']:
            pcc_config = submission['configs']['pcc_config']
            if isinstance(pcc_config, dict):
                submission['pcc_ip_address'] = pcc_config.get('ip', '')
                submission['pcc_subnet_mask'] = pcc_config.get('subnet', '')
        elif 'pcc_config' in submission and isinstance(submission['pcc_config'], dict):
            submission['pcc_ip_address'] = submission['pcc_config'].get('ip', '')
            submission['pcc_subnet_mask'] = submission['pcc_config'].get('subnet', '')
        else:
            # ถ้าไม่พบข้อมูล PC-C ใส่ค่าว่าง
            submission['pcc_ip_address'] = ''
            submission['pcc_subnet_mask'] = ''
    elif lab_num == 6:
        # Lab 6 - Router-on-a-Stick Inter-VLAN
        lab_devices = {
            "routers": ["R1"],
            "switches": ["S1", "S2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["Router-on-a-Stick", "VLANs"]
        }
        
        # ดึงข้อมูล Router Configuration
        if 'configs' in submission and isinstance(submission['configs'], dict):
            if 'r1_config' in submission['configs']:
                submission['r1_config'] = submission['configs']['r1_config']
            else:
                submission['r1_config'] = submission.get('switch_config', 'ไม่มีข้อมูล')
        else:
            submission['r1_config'] = submission.get('switch_config', 'ไม่มีข้อมูล')
        
        # ดึงข้อมูล Switch Configurations
        if 'configs' in submission and isinstance(submission['configs'], dict):
            if 'sw1_config' in submission['configs']:
                submission['sw1_config'] = submission['configs']['sw1_config']
            else:
                submission['sw1_config'] = 'ไม่มีข้อมูล'
            
            if 'sw2_config' in submission['configs']:
                submission['sw2_config'] = submission['configs']['sw2_config']
            else:
                submission['sw2_config'] = 'ไม่มีข้อมูล'
        else:
            submission['sw1_config'] = 'ไม่มีข้อมูล'
            submission['sw2_config'] = 'ไม่มีข้อมูล'
        
        # PC Config สำหรับ PC-A
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pca_config' in submission['configs']:
            pca_config = submission['configs']['pca_config']
            if isinstance(pca_config, dict):
                submission['pca_ip_address'] = pca_config.get('ip', '')
                submission['pca_subnet_mask'] = pca_config.get('subnet', '')
                submission['pca_default_gateway'] = pca_config.get('gateway', '')
        elif 'pca_config' in submission and isinstance(submission['pca_config'], dict):
            submission['pca_ip_address'] = submission['pca_config'].get('ip', '')
            submission['pca_subnet_mask'] = submission['pca_config'].get('subnet', '')
            submission['pca_default_gateway'] = submission['pca_config'].get('gateway', '')
        else:
            # ถ้าไม่มีข้อมูลเฉพาะเจาะจงของ PC-A ลองดึงจากข้อมูลทั่วไป
            submission['pca_ip_address'] = submission.get('pc_ip_address', '')
            submission['pca_subnet_mask'] = submission.get('pc_subnet_mask', '')
            submission['pca_default_gateway'] = submission.get('pc_default_gateway', '')
        
        # PC Config สำหรับ PC-B
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pcb_config' in submission['configs']:
            pcb_config = submission['configs']['pcb_config']
            if isinstance(pcb_config, dict):
                submission['pcb_ip_address'] = pcb_config.get('ip', '')
                submission['pcb_subnet_mask'] = pcb_config.get('subnet', '')
                submission['pcb_default_gateway'] = pcb_config.get('gateway', '')
        elif 'pcb_config' in submission and isinstance(submission['pcb_config'], dict):
            submission['pcb_ip_address'] = submission['pcb_config'].get('ip', '')
            submission['pcb_subnet_mask'] = submission['pcb_config'].get('subnet', '')
            submission['pcb_default_gateway'] = submission['pcb_config'].get('gateway', '')
        else:
            # ถ้าไม่พบข้อมูล PC-B ใส่ค่าว่าง
            submission['pcb_ip_address'] = ''
            submission['pcb_subnet_mask'] = ''
            submission['pcb_default_gateway'] = ''
    elif lab_num == 7:
        # Lab 7 - Inter-VLAN Routing
        lab_devices = {
            "routers": ["R1"],
            "switches": ["S1", "S2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["Inter-VLAN Routing"]
        }
        
        # ดึงข้อมูล Router Configuration
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('switch_config', 'ไม่มีข้อมูล')
        )
        
        # ดึงข้อมูล Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            'ไม่มีข้อมูล'
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            'ไม่มีข้อมูล'
        )
        
        # PC Config สำหรับ PC-A
        pca_config = submission.get('pca_config', submission.get('pc_a_config', {}))
        if isinstance(pca_config, dict):
            pc_a_config = {
                "ip": pca_config.get('ip', '192.168.20.3'),
                "subnet": pca_config.get('subnet', '255.255.255.0'),
                "gateway": pca_config.get('gateway', '192.168.20.1')
            }
        else:
            pc_a_config = {
                "ip": submission.get('pca_ip_address', '192.168.20.3'),
                "subnet": submission.get('pca_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pca_default_gateway', '192.168.20.1')
            }
        
        # PC Config สำหรับ PC-B
        pcb_config = submission.get('pcb_config', submission.get('pc_b_config', {}))
        if isinstance(pcb_config, dict):
            pc_b_config = {
                "ip": pcb_config.get('ip', '192.168.30.3'),
                "subnet": pcb_config.get('subnet', '255.255.255.0'),
                "gateway": pcb_config.get('gateway', '192.168.30.1')
            }
        else:
            pc_b_config = {
                "ip": submission.get('pcb_ip_address', '192.168.30.3'),
                "subnet": submission.get('pcb_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pcb_default_gateway', '192.168.30.1')
            }
    elif lab_num == 8:
        # Lab 8 - EtherChannel
        lab_devices = {
            "switches": ["S1", "S2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["EtherChannel", "PAgP/LACP"]
        }
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('switch_config', 'ไม่มีข้อมูล')
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            'ไม่มีข้อมูล'
        )
        
        # PC config สำหรับ Lab 8
        pca_config = {
            "ip": submission.get('pca_ip_address', submission.get('pc_ip_address', '192.168.20.3')),
            "subnet": submission.get('pca_subnet_mask', submission.get('pc_subnet_mask', '255.255.255.0'))
        }
        
        pcb_config = {
            "ip": submission.get('pcb_ip_address', '192.168.20.4'),
            "subnet": submission.get('pcb_subnet_mask', '255.255.255.0')
        }
    
        # PC Configuration สำหรับ PC-B
        pcb_config_data = submission.get('pcb_config', submission.get('pc_b_config', {}))
        if isinstance(pcb_config_data, dict):
            pc_b_config = {
                "ip": pcb_config_data.get('ip', '192.168.20.4'),
                "subnet": pcb_config_data.get('subnet', '255.255.255.0')
            }
        else:
            pc_b_config = {
                "ip": submission.get('pcb_ip_address', '192.168.20.4'),
                "subnet": submission.get('pcb_subnet_mask', '255.255.255.0')
            }

    elif lab_num == 9:
        # Lab 9 - PPP Authentication
        lab_devices = {
            "routers": ["Branch1", "Central", "Branch3"],
            "pcs": ["PC-A", "PC-C"],
            "features": ["PPP Authentication", "CHAP"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        submission['r3_config'] = (
            submission.get('configs', {}).get('r3_config', '') or 
            submission.get('r3_config', 'ไม่มีข้อมูล')
        )
        
        # PC Configuration สำหรับ PC-A
        pca_config_data = submission.get('pca_config', submission.get('pc_a_config', {}))
        if isinstance(pca_config_data, dict):
            pca_config = {
                "ip": pca_config_data.get('ip', '192.168.1.3'),
                "subnet": pca_config_data.get('subnet', '255.255.255.0'),
                "gateway": pca_config_data.get('gateway', '192.168.1.1'),
                "status": pca_config_data.get('status', 'ทดสอบ')
            }
        else:
            pca_config = {
                "ip": submission.get('pca_ip_address', '192.168.1.3'),
                "subnet": submission.get('pca_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pca_default_gateway', '192.168.1.1'),
                "status": submission.get('pca_status', 'ทดสอบ')
            }
        
        # PC Configuration สำหรับ PC-C
        pcc_config_data = submission.get('pcc_config', submission.get('pc_c_config', {}))
        if isinstance(pcc_config_data, dict):
            pcc_config = {
                "ip": pcc_config_data.get('ip', '192.168.3.3'),
                "subnet": pcc_config_data.get('subnet', '255.255.255.0'),
                "gateway": pcc_config_data.get('gateway', '192.168.3.1'),
                "status": pcc_config_data.get('status', 'ทดสอบ')
            }
        else:
            pcc_config = {
                "ip": submission.get('pcc_ip_address', '192.168.3.3'),
                "subnet": submission.get('pcc_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pcc_default_gateway', '192.168.3.1'),
                "status": submission.get('pcc_status', 'ทดสอบ')
            }
    elif lab_num == 10:
        # Lab 10 - NAT/PAT
        lab_devices = {
            "routers": ["Router 1", "Router 2 (ISP)", "Router 3"],
            "switches": ["Switch 1", "Switch 3"],
            "pcs": ["PC-A", "PC-C"],
            "features": ["NAT", "PAT"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        submission['r3_config'] = (
            submission.get('configs', {}).get('r3_config', '') or 
            submission.get('r3_config', 'ไม่มีข้อมูล')
        )
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('sw1_config', 'ไม่มีข้อมูล')
        )
        submission['sw3_config'] = (
            submission.get('configs', {}).get('sw3_config', '') or 
            submission.get('sw3_config', 'ไม่มีข้อมูล')
        )
        
        # PC Configuration สำหรับ PC-A
        pca_config_data = submission.get('pca_config', submission.get('pc_a_config', {}))
        if isinstance(pca_config_data, dict):
            pca_config = {
                "ip": pca_config_data.get('ip', '192.168.10.3'),
                "subnet": pca_config_data.get('subnet', '255.255.255.0'),
                "gateway": pca_config_data.get('gateway', '192.168.10.1')
            }
        else:
            pca_config = {
                "ip": submission.get('pca_ip_address', '192.168.10.3'),
                "subnet": submission.get('pca_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pca_default_gateway', '192.168.10.1')
            }
        
        # PC Configuration สำหรับ PC-C
        pcc_config_data = submission.get('pcc_config', submission.get('pc_c_config', {}))
        if isinstance(pcc_config_data, dict):
            pcc_config = {
                "ip": pcc_config_data.get('ip', '192.168.30.3'),
                "subnet": pcc_config_data.get('subnet', '255.255.255.0'),
                "gateway": pcc_config_data.get('gateway', '192.168.30.1')
            }
        else:
            pcc_config = {
                "ip": submission.get('pcc_ip_address', '192.168.30.3'),
                "subnet": submission.get('pcc_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pcc_default_gateway', '192.168.30.1')
            }

    elif lab_num == 11:
        # Lab 11 - VLAN
        lab_devices = {
            "routers": ["Router 1", "Router 2"],
            "switches": ["Switch 1", "Switch 2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["VLAN", "Inter-VLAN Routing"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('sw1_config', 'ไม่มีข้อมูล')
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            submission.get('sw2_config', 'ไม่มีข้อมูล')
        )
        
        # PC Configuration สำหรับ PC-A
        pca_config_data = submission.get('pca_config', submission.get('pc_a_config', {}))
        if isinstance(pca_config_data, dict):
            pca_config = {
                "ip": pca_config_data.get('ip', '10.30.0.10'),
                "subnet": pca_config_data.get('subnet', '255.255.255.0'),
                "gateway": pca_config_data.get('gateway', '10.30.0.1')
            }
        else:
            pca_config = {
                "ip": submission.get('pca_ip_address', '10.30.0.10'),
                "subnet": submission.get('pca_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pca_default_gateway', '10.30.0.1')
            }
        
        # PC Configuration สำหรับ PC-B
        pcb_config_data = submission.get('pcb_config', submission.get('pc_b_config', {}))
        if isinstance(pcb_config_data, dict):
            pcb_config = {
                "ip": pcb_config_data.get('ip', '10.40.0.10'),
                "subnet": pcb_config_data.get('subnet', '255.255.255.0'),
                "gateway": pcb_config_data.get('gateway', '10.40.0.1')
            }
        else:
            pcb_config = {
                "ip": submission.get('pcb_ip_address', '10.40.0.10'),
                "subnet": submission.get('pcb_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pcb_default_gateway', '10.40.0.1')
            }

    elif lab_num == 12:
        # Lab 12 - DHCPv4
        lab_devices = {
            "routers": ["Router 1", "Router 2"],
            "switches": ["Switch 1", "Switch 2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["DHCPv4", "DHCP Server", "DHCP Relay"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('sw1_config', 'ไม่มีข้อมูล')
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            submission.get('sw2_config', 'ไม่มีข้อมูล')
        )
        
        # VLAN Configurations
        submission['vlan_sw1'] = submission.get('configs', {}).get('vlan_sw1', 'ไม่มีข้อมูล VLAN')
        submission['vlan_sw2'] = submission.get('configs', {}).get('vlan_sw2', 'ไม่มีข้อมูล VLAN')
        
        # PC Configuration สำหรับ PC-A
        pca_config_data = submission.get('pca_config', submission.get('pc_a_config', {}))
        if isinstance(pca_config_data, dict):
            pca_config = {
                "ip": pca_config_data.get('ip', '192.168.1.3'),
                "subnet": pca_config_data.get('subnet', '255.255.255.192'),
                "gateway": pca_config_data.get('gateway', '192.168.1.1')
            }
        else:
            pca_config = {
                "ip": submission.get('pca_ip_address', '192.168.1.3'),
                "subnet": submission.get('pca_subnet_mask', '255.255.255.192'),
                "gateway": submission.get('pca_default_gateway', '192.168.1.1')
            }
        
        # PC Configuration สำหรับ PC-B
        pcb_config_data = submission.get('pcb_config', submission.get('pc_b_config', {}))
        if isinstance(pcb_config_data, dict):
            pcb_config = {
                "ip": pcb_config_data.get('ip', '192.168.1.100'),
                "subnet": pcb_config_data.get('subnet', '255.255.255.240'),
                "gateway": pcb_config_data.get('gateway', '192.168.1.97')
            }
        else:
            pcb_config = {
                "ip": submission.get('pcb_ip_address', '192.168.1.100'),
                "subnet": submission.get('pcb_subnet_mask', '255.255.255.240'),
                "gateway": submission.get('pcb_default_gateway', '192.168.1.97')
            }
        
        # DHCP Configuration
        submission['dhcp_config'] = submission.get('configs', {}).get('dhcp_config', 'DHCP Server: R1\nDHCP Relay: R2 (Helper address: 10.0.0.1)')
    elif lab_num == 13:
        # Lab 13 - DHCPv6
        lab_devices = {
            "routers": ["Router 1", "Router 2"],
            "switches": ["Switch 1", "Switch 2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["IPv6", "DHCPv6"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('sw1_config', 'ไม่มีข้อมูล')
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            submission.get('sw2_config', 'ไม่มีข้อมูล')
        )
        
        # PC Configuration สำหรับ PC-A
        pc_a_config = {
            "ip": submission.get('configs', {}).get('pca_config', {}).get('ip', '2001:db8:acad:1::'),
            "subnet": "64"
        }
        
        # PC Configuration สำหรับ PC-B
        pc_b_config = {
            "ip": submission.get('configs', {}).get('pcb_config', {}).get('ip', '2001:db8:acad:3::'),
            "subnet": "64"
        }
    elif lab_num == 14:
        # Lab 14 - Static Routing
        lab_devices = {
            "routers": ["Router 1", "Router 2"],
            "switches": ["Switch 1", "Switch 2"],
            "pcs": ["PC-A", "PC-B"],
            "features": ["Static Routing", "Network Configuration"]
        }
        
        # Router Configurations
        submission['r1_config'] = (
            submission.get('configs', {}).get('r1_config', '') or 
            submission.get('r1_config', 'ไม่มีข้อมูล')
        )
        submission['r2_config'] = (
            submission.get('configs', {}).get('r2_config', '') or 
            submission.get('r2_config', 'ไม่มีข้อมูล')
        )
        
        # Switch Configurations
        submission['sw1_config'] = (
            submission.get('configs', {}).get('sw1_config', '') or 
            submission.get('sw1_config', 'ไม่มีข้อมูล')
        )
        submission['sw2_config'] = (
            submission.get('configs', {}).get('sw2_config', '') or 
            submission.get('sw2_config', 'ไม่มีข้อมูล')
        )
        
        # PC Configuration สำหรับ PC-A
        pc_a_config = {
            "ip": submission.get('configs', {}).get('pca_config', {}).get('ip', '192.168.1.2'),
            "subnet": submission.get('configs', {}).get('pca_config', {}).get('subnet', '255.255.255.0'),
            "gateway": submission.get('configs', {}).get('pca_config', {}).get('gateway', '192.168.1.1')
        }
        
        # PC Configuration สำหรับ PC-B
        pc_b_config = {
            "ip": submission.get('configs', {}).get('pcb_config', {}).get('ip', '192.168.1.3'),
            "subnet": submission.get('configs', {}).get('pcb_config', {}).get('subnet', '255.255.255.0'),
            "gateway": submission.get('configs', {}).get('pcb_config', {}).get('gateway', '192.168.1.1')
        }
    elif lab_num == 15:
        # Lab 15 - HSRP
        lab_devices = {
            "routers": ["R1", "R2", "R3"],
            "switches": ["S1", "S3"],
            "pcs": ["PC-A", "PC-C"],
            "features": ["HSRP", "Router Redundancy"]
        }
        
        # ตรวจสอบว่า submission เป็น dictionary หรือไม่
        if not isinstance(submission, dict):
            submission = {}
        
        # ตรวจสอบว่ามี configs อยู่หรือไม่
        if 'configs' in submission and isinstance(submission['configs'], dict):
            # ถ้ามี configs ให้ดึงข้อมูลจาก configs มาใส่ใน submission
            submission['r1_config'] = submission['configs'].get('r1_config', 'ไม่มีข้อมูล')
            submission['r2_config'] = submission['configs'].get('r2_config', 'ไม่มีข้อมูล')
            submission['r3_config'] = submission['configs'].get('r3_config', 'ไม่มีข้อมูล')
            submission['sw1_config'] = submission['configs'].get('sw1_config', 'ไม่มีข้อมูล')
            submission['sw2_config'] = submission['configs'].get('sw2_config', 'ไม่มีข้อมูล')
        else:
            # ถ้าไม่มี configs ให้กำหนดค่าเริ่มต้น
            if 'r1_config' not in submission:
                submission['r1_config'] = 'ไม่มีข้อมูล'
            if 'r2_config' not in submission:
                submission['r2_config'] = 'ไม่มีข้อมูล'
            if 'r3_config' not in submission:
                submission['r3_config'] = 'ไม่มีข้อมูล'
            if 'sw1_config' not in submission:
                submission['sw1_config'] = 'ไม่มีข้อมูล'
            if 'sw2_config' not in submission:
                submission['sw2_config'] = 'ไม่มีข้อมูล'
        
        # PC-A config
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pca_config' in submission['configs']:
            pca_config_data = submission['configs']['pca_config']
            if isinstance(pca_config_data, dict):
                pc_a_config = {
                    "ip": pca_config_data.get('ip', '192.168.1.31'),
                    "subnet": pca_config_data.get('subnet', '255.255.255.0'),
                    "gateway": pca_config_data.get('gateway', '192.168.1.1')
                }
            else:
                pc_a_config = {
                    "ip": "192.168.1.31",
                    "subnet": "255.255.255.0",
                    "gateway": "192.168.1.254"
                }
        else:
            pc_a_config = {
                "ip": submission.get('pca_ip_address', submission.get('pc_ip_address', '192.168.1.31')),
                "subnet": submission.get('pca_subnet_mask', submission.get('pc_subnet_mask', '255.255.255.0')),
                "gateway": submission.get('pca_default_gateway', submission.get('pc_default_gateway', '192.168.1.254'))
            }
        
        # PC-C config
        if 'configs' in submission and isinstance(submission['configs'], dict) and 'pcc_config' in submission['configs']:
            pcc_config_data = submission['configs']['pcc_config']
            if isinstance(pcc_config_data, dict):
                pc_c_config = {
                    "ip": pcc_config_data.get('ip', '192.168.1.33'),
                    "subnet": pcc_config_data.get('subnet', '255.255.255.0'),
                    "gateway": pcc_config_data.get('gateway', '192.168.1.1')
                }
            else:
                pc_c_config = {
                    "ip": "192.168.1.33",
                    "subnet": "255.255.255.0",
                    "gateway": "192.168.1.254"
                }
        else:
            pc_c_config = {
                "ip": submission.get('pcc_ip_address', '192.168.1.33'),
                "subnet": submission.get('pcc_subnet_mask', '255.255.255.0'),
                "gateway": submission.get('pcc_default_gateway', '192.168.1.254')
            }
        
        # แก้ไขปัญหาตัวแปรที่สับสน - ตรวจสอบว่ามีการใช้ชื่อตัวแปรที่แตกต่างกัน
        if 'pc_a_config' not in locals():
            pc_a_config = pca_config if 'pca_config' in locals() else {
                "ip": "192.168.1.31",
                "subnet": "255.255.255.0",
                "gateway": "192.168.1.254"
            }
            
        if 'pc_c_config' not in locals():
            pc_c_config = pcc_config if 'pcc_config' in locals() else {
                "ip": "192.168.1.33",
                "subnet": "255.255.255.0", 
                "gateway": "192.168.1.254"
            }

    elif lab_num == 16:
    # Lab 16 - Switch Security Configuration
        lab_devices = {
            "routers": ["R1"],
            "switches": ["S1", "S2"],
            "features": ["Port Security", "BPDU Guard", "DHCP Snooping"]
        }
        
        # ตรวจสอบว่า submission เป็น dictionary หรือไม่
        if not isinstance(submission, dict):
            submission = {}
        
        # ดึงข้อมูลจาก configs โดยตรง
        if 'configs' in submission and isinstance(submission['configs'], dict):
            submission['r1_config'] = submission['configs'].get('r1_config', 'ไม่มีข้อมูล')
            submission['sw1_config'] = submission['configs'].get('sw1_config', 'ไม่มีข้อมูล')
            submission['sw2_config'] = submission['configs'].get('sw2_config', 'ไม่มีข้อมูล')
        else:
            # กรณีไม่มี configs ให้ใช้ค่าเริ่มต้น
            submission['r1_config'] = submission.get('r1_config', 'ไม่มีข้อมูล')
            submission['sw1_config'] = submission.get('sw1_config', 'ไม่มีข้อมูล')
            submission['sw2_config'] = submission.get('sw2_config', 'ไม่มีข้อมูล')
        
        # ตั้งค่าความปลอดภัยต่างๆ (มีค่าเริ่มต้นเป็น Enabled)
        submission['port_security'] = 'Enabled'
        submission['dhcp_snooping'] = 'Enabled'
        submission['bpdu_guard'] = 'Enabled'
    
    # คำนวณคะแนนและสถานะ
    try:
        score = float(submission['switch_score'].split('/')[0])
        status = 'completed' if score >= 60 else 'in_progress'
        status_text = 'เสร็จสมบูรณ์' if score >= 60 else 'ยังไม่สมบูรณ์'
    except Exception:
        score = 0
        status = 'in_progress'
        status_text = 'ยังไม่สมบูรณ์'
    
    submission['score'] = score
    submission['status'] = status
    submission['status_text'] = status_text
    
    # เพิ่มข้อมูลชื่อแล็บลงใน submission
    submission['lab_title'] = lab_titles.get(lab_num, f"Lab {lab_num}")
    
    # กำหนดรายละเอียดแล็บ
    lab_details = {
        1: {
            "title": "Basic Switch Configuration",
            "description": "การตั้งค่าพื้นฐานของ Switch และการเชื่อมต่อกับ PC",
            "objectives": ["ตั้งค่า Switch ให้มีความปลอดภัย", "กำหนด IP Address ให้กับ PC", "ทดสอบการเชื่อมต่อ"]
        },
        2: {
            "title": "Configure VLANs and Trunking",
            "description": "การกำหนด VLANs และ Trunk Links",
            "objectives": ["สร้าง VLANs", "กำหนด Trunk Links", "ตั้งค่า PC ในแต่ละ VLAN"]
        },
        3: {
            "title": "Implement VLANs and Trunking",
            "description": "การใช้งาน VLANs และการกำหนดค่า Trunking ระหว่าง Switches",
            "objectives": ["กำหนด VLANs", "ตั้งค่า Trunk Ports", "ตั้งค่า Access Ports", "ตั้งค่า PCs ให้สื่อสารได้ภายใน VLAN"]
        },
        4: {
            "title": "Redundant Links",
            "description": "การใช้ Spanning Tree Protocol เพื่อจัดการ Redundant Links",
            "objectives": ["ตั้งค่า Redundant Links", "ศึกษาการทำงานของ STP", "ทำความเข้าใจ Port States ของ STP"]
        },
        5: {
            "title": "Rapid PVST+",
            "description": "การใช้งาน Rapid PVST+ เพื่อจัดการ Redundant Links",
            "objectives": ["ตั้งค่า Rapid PVST+", "ตั้งค่า PortFast และ BPDU Guard", "เปรียบเทียบกับ PVST+ ปกติ"]
        },
        6: {
            "title": "Router-on-a-Stick Inter-VLAN",
            "description": "การใช้ Router เพื่อเชื่อมต่อระหว่าง VLANs",
            "objectives": ["ตั้งค่า Router-on-a-Stick", "กำหนด Subinterfaces", "ทดสอบการสื่อสารระหว่าง VLANs"]
        },
        7: {
            "title": "Inter-VLAN Routing",
            "description": "การเชื่อมต่อระหว่าง VLANs โดยใช้ Router",
            "objectives": ["กำหนด VLANs", "ตั้งค่า Router-on-a-Stick", "ทดสอบการสื่อสารระหว่าง VLANs"]
        },
        8: {
            "title": "EtherChannel",
            "description": "การรวมหลาย Physical Links เข้าด้วยกันใช้ EtherChannel",
            "objectives": ["กำหนด EtherChannel ระหว่าง Switches", "ใช้ PAgP หรือ LACP", "ทดสอบการทำงานของ EtherChannel"]
        },
        9: {
            "title": "PPP Authentication",
            "description": "การตั้งค่า PPP Authentication ระหว่าง Routers",
            "objectives": ["กำหนด PPP Encapsulation", "ตั้งค่า CHAP Authentication", "ทดสอบการเชื่อมต่อ"]
        },
        10: {
            "title": "Standard IPv4 ACLs",
            "description": "การใช้ Standard Access Control Lists เพื่อควบคุมการเข้าถึงเครือข่าย",
            "objectives": ["กำหนด Standard ACLs", "ประยุกต์ใช้งาน ACLs กับ Interfaces", "ทดสอบ ACL Functionality"]
        },
        11: {
            "title": "Extended IPv4 ACLs",
            "description": "การใช้ Extended Access Control Lists เพื่อควบคุมการเข้าถึงเครือข่ายอย่างละเอียด",
            "objectives": ["กำหนด Extended ACLs", "ประยุกต์ใช้งาน ACLs กับ Interfaces", "ทดสอบ ACL Functionality"]
        },
        12: {
            "title": "DHCPv4",
            "description": "การตั้งค่า DHCP Server และ DHCP Relay",
            "objectives": ["กำหนด DHCP Server", "ตั้งค่า DHCP Relay", "ทดสอบการจัดสรร IP Address"]
        },
        13: {
            "title": "DHCPv6",
            "description": "การตั้งค่า DHCPv6 Server และ Client",
            "objectives": ["กำหนด DHCPv6 Stateless", "ตั้งค่า DHCPv6 Stateful", "ทดสอบการจัดสรร IPv6 Address"]
        },
        14: {
            "title": "Static Route Configuration",
            "description": "การกำหนด Static Routes บน Routers",
            "objectives": ["กำหนด Static Routes", "กำหนด Default Routes", "ทดสอบการเชื่อมต่อระหว่างเครือข่าย"]
        },
        15: {
            "title": "HSRP",
            "description": "การใช้ Hot Standby Router Protocol เพื่อรองรับ Router Redundancy",
            "objectives": ["กำหนด HSRP", "ตั้งค่า Priority และ Preemption", "ทดสอบ Router Failover"]
        },
        16: {
            "title": "Switch Security Configuration",
            "description": "การตั้งค่าความปลอดภัยบน Switch",
            "objectives": ["กำหนด Port Security", "ตั้งค่า DHCP Snooping", "ตั้งค่า BPDU Guard", "ทดสอบความปลอดภัยของ Switch"]
        }
    }
    
    # เตรียมข้อมูลสรุปสำหรับประวัติการส่งงาน
    submission_history = {
        "timestamp": submission.get('timestamp', 'ไม่ระบุ').replace(microsecond=0),
        "submitted_by": f"{student.get('first_name', '')} {student.get('last_name', '')}",
        "status": status_text,
        "score": score
    }
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # Debug: แสดงข้อมูลใน log
    print(f"Lab {lab_num} Data:", submission)
    
    # ส่งข้อมูลไปยัง template
    return render_template('view_submission.html',
                          lab_num=lab_num,
                          student=student,
                          submission=submission,
                          pc_config=pc_config,
                          pc1_config=pc1_config,
                          pc2_config=pc2_config,
                          pca_config=pca_config,
                          pcb_config=pcb_config,
                          pcc_config=pcc_config,
                          pc_a_config=pc_a_config,
                          pc_b_config=pc_b_config,
                          pc_c_config=pc_c_config,
                          lab_devices=lab_devices,            # อุปกรณ์แต่ละ Lab
                          lab_details=lab_details.get(lab_num, {}),  # รายละเอียดของ Lab
                          submission_history=submission_history,     # ประวัติการส่งงาน
                          first_name=first_name,
                          last_name=last_name)

# อัพเดทคะแนนด้วยตนเอง
@teacher_bp.route('/update_grade', methods=['POST'])
def update_grade():
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
            "manual_graded_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        }}
    )
    
    flash('อัพเดทคะแนนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('teacher.view_submission', lab_num=lab_num, student_id=student_id))

# ลบการส่งงาน
@teacher_bp.route('/delete_submission', methods=['POST'])
def delete_submission():
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok").replace(microsecond=0)).strftime("%Y-%m-%d %H:%M:%S")
                }},
                upsert=True
            )
        elif lab_num == 3:
            # อัพเดทสำหรับ Lab 3
            sw1_keywords_text = request.form.get('sw1_keywords', '')
            sw2_keywords_text = request.form.get('sw2_keywords', '')
            expected_vlans_sw1_text = request.form.get('expected_vlans_sw1', '{}')
            expected_vlans_sw2_text = request.form.get('expected_vlans_sw2', '{}')
            pc1_ip = request.form.get('pc1_ip', '')
            pc1_subnet = request.form.get('pc1_subnet', '')
            pc1_gateway = request.form.get('pc1_gateway', '')
            pc2_ip = request.form.get('pc2_ip', '')
            pc2_subnet = request.form.get('pc2_subnet', '')
            pc2_gateway = request.form.get('pc2_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            sw1_keywords = parse_keywords_from_text(sw1_keywords_text)
            sw2_keywords = parse_keywords_from_text(sw2_keywords_text)
            
            # แปลง JSON string เป็น Python object
            try:
                expected_vlans_sw1 = json.loads(expected_vlans_sw1_text)
                expected_vlans_sw2 = json.loads(expected_vlans_sw2_text)
            except json.JSONDecodeError:
                expected_vlans_sw1 = {}
                expected_vlans_sw2 = {}
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "sw1_keywords": sw1_keywords,
                    "sw2_keywords": sw2_keywords,
                    "expected_vlans_sw1": expected_vlans_sw1,
                    "expected_vlans_sw2": expected_vlans_sw2,
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok").replace(microsecond=0)).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                }},
                upsert=True
            )
    
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

@teacher_bp.route('/lab/<int:lab_num>/reset', methods=['GET'])
def reset_lab_data(lab_num):
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ลบข้อมูลการส่งงานทั้งหมดในแล็บนี้
        delete_result = scores_collection.delete_many({"lab": f"Lab {lab_num}"})
        deleted_count = delete_result.deleted_count
        
        flash(f'ลบข้อมูลการส่งงานเรียบร้อยแล้ว {deleted_count} รายการ', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการลบข้อมูล: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.lab_management', lab_num=lab_num))

@teacher_bp.route('/lab/<int:lab_num>/keyword_history')
def view_keyword_history(lab_num):
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงประวัติการแก้ไขคีย์เวิร์ด
    keyword_history = list(lab_keywords_collection.find(
        {"lab_num": lab_num}
    ).sort("updated_at", -1))  # เรียงจากใหม่ไปเก่า
    
    # ถ้าไม่มีประวัติ
    if not keyword_history:
        flash('ไม่พบประวัติการแก้ไขคีย์เวิร์ดสำหรับแล็บนี้', 'info')
        return redirect(url_for('teacher.lab_management', lab_num=lab_num))
    
    # ดึงข้อมูลผู้ใช้
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # ชื่อแล็บ
    lab_titles = {
        1: "Basic Switch Configuration",
        # เพิ่มชื่อแล็บอื่นๆ
    }
    
    return render_template('keyword_history.html', 
                          lab_num=lab_num,
                          lab_title=lab_titles.get(lab_num, f"Lab {lab_num}"),
                          keyword_history=keyword_history,
                          first_name=first_name,
                          last_name=last_name)