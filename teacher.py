from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from bson import ObjectId
import json
import re

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
    if not keywords:
        return ""
        
    formatted_text = ""
    
    for item in keywords:
        if isinstance(item, dict):
            for interface, commands in item.items():
                # เขียนชื่อ interface
                formatted_text += f"{interface}\n"
                # เขียนคำสั่งย่อย
                for cmd in commands:
                    formatted_text += f"  {cmd}\n"
        else:
            # เขียนคำสั่งปกติ
            formatted_text += f"{item}\n"
    
    return formatted_text.rstrip()

# แสดงหน้าจัดการแล็บ
# แสดงหน้าจัดการแล็บ
@teacher_bp.route('/lab/<int:lab_num>')
def lab_management(lab_num):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูล keyword ของแล็บนี้
    lab_keywords = lab_keywords_collection.find_one({"lab_num": lab_num})

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
        elif lab_num == 3:
            # ตัวอย่างสำหรับ Lab 3 จากไฟล์ lab3.py
            switch1_keywords = [
                "hostname S1",
                "no ip domain-lookup",
                {"interface FastEthernet0/1": ["switchport trunk native vlan 1000", "switchport trunk allowed vlan 10,20,30,1000", "switchport mode trunk"]},
                {"interface FastEthernet0/6": ["switchport access vlan 20", "switchport mode access"]},
                {"interface Vlan1": ["no ip address"]},
                {"interface Vlan10": ["ip address 192.168.10.11 255.255.255.0"]},
                {"interface Vlan20": ["ip address 192.168.20.11 255.255.255.0"]},
                {"interface Vlan30": ["ip address 192.168.30.11 255.255.255.0"]}
            ]

            switch2_keywords = [
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
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans_sw1": expected_vlans_sw1,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "expected_vlans_sw1": expected_vlans_sw1,
                "expected_vlans_sw2": expected_vlans_sw2,
                "pc1_config": pc1_config,
                "pc2_config": pc2_config
            }
        elif lab_num == 4:
            # ตัวอย่างสำหรับ Lab 4 จากไฟล์ lab4.py
            switch1_keywords = [
                "hostname S1",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/1": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.1 255.255.255.0"]},
            ]
            
            switch2_keywords = [
                "hostname S2",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/2": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.2 255.255.255.0"]},
            ]
            
            switch3_keywords = [
                "hostname S3",
                "spanning-tree mode pvst",
                {"interface FastEthernet0/3": ["switchport mode trunk"]},
                {"interface Vlan1": ["ip address 192.168.1.3 255.255.255.0"]},
            ]
            
            spanning_tree_sw1 = {
                "Fa0/2": "Root FWD",
                "Fa0/4": "Altn BLK",
            }
            
            spanning_tree_sw2 = {
                "Fa0/2": "Desg FWD",
                "Fa0/4": "Desg FWD",
            }
            
            spanning_tree_sw3 = {
                "Fa0/2": "Root FWD",
                "Fa0/4": "Desg FWD",
            }
            
            # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
            lab_keywords_collection.insert_one({
                "lab_num": lab_num,
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "switch3_keywords": switch3_keywords,
                "spanning_tree_sw1": spanning_tree_sw1,
                "spanning_tree_sw2": spanning_tree_sw2,
                "spanning_tree_sw3": spanning_tree_sw3,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
            
            lab_keywords = {
                "switch1_keywords": switch1_keywords,
                "switch2_keywords": switch2_keywords,
                "switch3_keywords": switch3_keywords,
                "spanning_tree_sw1": spanning_tree_sw1,
                "spanning_tree_sw2": spanning_tree_sw2,
                "spanning_tree_sw3": spanning_tree_sw3
            }
        elif lab_num == 5:
            # ตรวจสอบว่า lab_keywords เป็น dict ที่มีค่าว่างหรือไม่
            if not lab_keywords or all(not val for val in lab_keywords.values() if val not in ['lab_num', 'general_keywords', 'created_at']):
                # ตั้งค่าเริ่มต้นสำหรับ Lab 5
                switch1_keywords = [
                    "hostname S1",
                    "spanning-tree mode rapid-pvst",
                    {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                    {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                    {"interface FastEthernet0/6": ["switchport access vlan 10", "switchport mode access", 
                                                "spanning-tree portfast", "spanning-tree bpduguard enable"]},
                    {"interface Vlan99": ["ip address 192.168.1.11 255.255.255.0"]}
                ]
                
                switch2_keywords = [
                    "hostname S2",
                    "spanning-tree mode rapid-pvst",
                    {"interface FastEthernet0/1": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                    {"interface FastEthernet0/3": ["switchport trunk native vlan 99", "switchport mode trunk"]},
                    {"interface Vlan99": ["ip address 192.168.1.12 255.255.255.0"]}
                ]
                
                switch3_keywords = [
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
                
                # ลบข้อมูลเดิมและสร้างใหม่
                lab_keywords_collection.delete_one({"lab_num": lab_num})
                
                # บันทึกลงฐานข้อมูลเพื่อใช้ครั้งต่อไป
                lab_keywords_collection.insert_one({
                    "lab_num": lab_num,
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "switch3_keywords": switch3_keywords,
                    "pca_config": pca_config,
                    "pcc_config": pcc_config,
                    "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                })
                
                lab_keywords = {
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "switch3_keywords": switch3_keywords,
                    "pca_config": pca_config,
                    "pcc_config": pcc_config
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
    switch3_keywords_text = ""
    general_keywords_text = ""
    
    if lab_num == 1:
        switch_keywords = lab_keywords.get('switch_keywords', [])
        switch_keywords_text = format_keywords_for_display(switch_keywords)
    elif lab_num == 2:
        switch1_keywords = lab_keywords.get('switch1_keywords', [])
        switch2_keywords = lab_keywords.get('switch2_keywords', [])
        switch1_keywords_text = format_keywords_for_display(switch1_keywords)
        switch2_keywords_text = format_keywords_for_display(switch2_keywords)
    elif lab_num == 3:
        switch1_keywords = lab_keywords.get('switch1_keywords', [])
        switch2_keywords = lab_keywords.get('switch2_keywords', [])
        switch1_keywords_text = format_keywords_for_display(switch1_keywords)
        switch2_keywords_text = format_keywords_for_display(switch2_keywords)
    elif lab_num == 4:
        switch1_keywords = lab_keywords.get('switch1_keywords', [])
        switch2_keywords = lab_keywords.get('switch2_keywords', [])
        switch3_keywords = lab_keywords.get('switch3_keywords', [])
        switch1_keywords_text = format_keywords_for_display(switch1_keywords)
        switch2_keywords_text = format_keywords_for_display(switch2_keywords)
        switch3_keywords_text = format_keywords_for_display(switch3_keywords)
    elif lab_num == 5:
        switch1_keywords = lab_keywords.get('switch1_keywords', [])
        switch2_keywords = lab_keywords.get('switch2_keywords', [])
        switch3_keywords = lab_keywords.get('switch3_keywords', [])
        switch1_keywords_text = format_keywords_for_display(switch1_keywords)
        switch2_keywords_text = format_keywords_for_display(switch2_keywords)
        switch3_keywords_text = format_keywords_for_display(switch3_keywords)
    else:
        general_keywords = lab_keywords.get('general_keywords', [])
        general_keywords_text = format_keywords_for_display(general_keywords)
    
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
                        switch3_keywords_text=switch3_keywords_text,
                        general_keywords_text=general_keywords_text,
                        pc_config=lab_keywords.get('pc_config', {}),
                        pc1_config=lab_keywords.get('pc1_config', {}),
                        pc2_config=lab_keywords.get('pc2_config', {}),
                        pca_config=lab_keywords.get('pca_config', {'ip': '', 'subnet': ''}),
                        pcc_config=lab_keywords.get('pcc_config', {'ip': '', 'subnet': ''}),
                        spanning_tree_sw1=lab_keywords.get('spanning_tree_sw1', {}),
                        spanning_tree_sw2=lab_keywords.get('spanning_tree_sw2', {}),
                        spanning_tree_sw3=lab_keywords.get('spanning_tree_sw3', {}),
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

def clean_keywords(keywords):
    """
    ทำความสะอาดคีย์เวิร์ด - ลบเครื่องหมาย quotes และอื่นๆ
    
    Parameters:
    keywords (list): รายการคีย์เวิร์ดที่ต้องการทำความสะอาด
    
    Returns:
    list: รายการคีย์เวิร์ดที่ทำความสะอาดแล้ว
    """
    clean_list = []
    
    for item in keywords:
        if isinstance(item, dict):
            clean_dict = {}
            for key, values in item.items():
                # ลบเครื่องหมาย quotes จากชื่อ interface
                clean_key = key.strip('"\'')
                # ลบเครื่องหมาย quotes จากคำสั่งใน interface
                clean_values = [val.strip('"\'"[]') for val in values]
                clean_dict[clean_key] = clean_values
            clean_list.append(clean_dict)
        else:
            # ลบเครื่องหมาย quotes จากคำสั่งทั่วไป
            clean_list.append(item.strip('"\''))
    
    return clean_list

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
    
    lines = text.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith('interface'):
            # เก็บ interface ก่อนหน้า (ถ้ามี)
            if current_interface and interface_commands:
                keywords.append({current_interface: interface_commands})
            
            # เริ่มต้นบล็อก interface ใหม่
            current_interface = line
            interface_commands = []
            
            # ดึงคำสั่งย่อยทั้งหมดของ interface นี้
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i].strip().startswith(' '):
                interface_commands.append(lines[i].strip())
                i += 1
            
            # เพิ่ม interface นี้พร้อมคำสั่งย่อยลงในรายการคีย์เวิร์ด
            keywords.append({current_interface: interface_commands})
            current_interface = None
            interface_commands = []
        else:
            # คีย์เวิร์ดปกติ
            keywords.append(line)
            i += 1
    
    return keywords

def format_vlan_config_for_display(vlan_config):
    """
    แปลง VLAN config เป็นข้อความสำหรับแสดงผล
    """
    if not vlan_config:
        return ""
    
    vlan_lines = []
    for vlan_id, vlan_data in vlan_config.items():
        vlan_line = f"{vlan_id}:{vlan_data['name']}"
        if vlan_data.get('ports'):  # ใช้ .get() เพื่อป้องกัน KeyError
            vlan_line += f":{','.join(vlan_data['ports'])}"
        vlan_lines.append(vlan_line)
    
    return "\n".join(vlan_lines)

def parse_vlan_config(vlan_config_text):
    """
    แปลง VLAN config text เป็น dictionary
    """
    vlan_configs = {}
    for line in vlan_config_text.strip().split('\n'):
        if line and ':' in line:
            parts = line.split(':')
            vlan_id = parts[0].strip()
            vlan_name = parts[1].strip()
            ports = parts[2].split(',') if len(parts) > 2 and parts[2].strip() else []
            
            vlan_configs[vlan_id] = {
                "name": vlan_name,
                "ports": [port.strip() for port in ports]
            }
    
    return vlan_configs
def format_spanning_config_for_display(spanning_config):
    """
    แปลง Spanning Tree config เป็นข้อความสำหรับแสดงผล
    """
    if not spanning_config:
        return ""
    
    spanning_lines = []
    for interface, state in spanning_config.items():
        spanning_lines.append(f"{interface}: {state}")
    
    return "\n".join(spanning_lines)
# อัพเดทคีย์เวิร์ด
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
            switch1_keywords_text = request.form.get('switch1_keywords', '')
            switch2_keywords_text = request.form.get('switch2_keywords', '')
            vlan_config_sw1_text = request.form.get('vlan_config_sw1', '')
            vlan_config_sw2_text = request.form.get('vlan_config_sw2', '')
            pc1_ip = request.form.get('pc1_ip', '')
            pc1_subnet = request.form.get('pc1_subnet', '')
            pc1_gateway = request.form.get('pc1_gateway', '')
            pc2_ip = request.form.get('pc2_ip', '')
            pc2_subnet = request.form.get('pc2_subnet', '')
            pc2_gateway = request.form.get('pc2_gateway', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            switch1_keywords = parse_keywords_from_text(switch1_keywords_text)
            switch2_keywords = parse_keywords_from_text(switch2_keywords_text)
            
            # แปลงข้อความการกำหนดค่า VLAN เป็นพจนานุกรม
            # หมายเหตุ: ในเว็บจะต้องใช้รูปแบบที่เฉพาะเจาะจงในการกรอกข้อมูล VLAN
            # เช่น "1:default:" หรือ "10:Management:Fa0/1,Fa0/2"
            
            expected_vlans_sw1 = {}
            for line in vlan_config_sw1_text.strip().split('\n'):
                if line and ":" in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        vlan_id = parts[0].strip()
                        vlan_name = parts[1].strip()
                        ports = []
                        if len(parts) > 2 and parts[2].strip():
                            ports = [port.strip() for port in parts[2].split(',')]
                        expected_vlans_sw1[vlan_id] = {
                            "name": vlan_name,
                            "ports": ports
                        }
            
            expected_vlans_sw2 = {}
            for line in vlan_config_sw2_text.strip().split('\n'):
                if line and ":" in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        vlan_id = parts[0].strip()
                        vlan_name = parts[1].strip()
                        ports = []
                        if len(parts) > 2 and parts[2].strip():
                            ports = [port.strip() for port in parts[2].split(',')]
                        expected_vlans_sw2[vlan_id] = {
                            "name": vlan_name,
                            "ports": ports
                        }
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )
        elif lab_num == 4:
            # อัพเดทสำหรับ Lab 4
            switch1_keywords_text = request.form.get('switch1_keywords', '')
            switch2_keywords_text = request.form.get('switch2_keywords', '')
            switch3_keywords_text = request.form.get('switch3_keywords', '')
            spanning_tree_sw1_text = request.form.get('spanning_tree_sw1', '')
            spanning_tree_sw2_text = request.form.get('spanning_tree_sw2', '')
            spanning_tree_sw3_text = request.form.get('spanning_tree_sw3', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            switch1_keywords = parse_keywords_from_text(switch1_keywords_text)
            switch2_keywords = parse_keywords_from_text(switch2_keywords_text)
            switch3_keywords = parse_keywords_from_text(switch3_keywords_text)
            
            # แปลงข้อความการกำหนดค่า Spanning Tree เป็นพจนานุกรม
            # หมายเหตุ: ในเว็บจะต้องใช้รูปแบบที่เฉพาะเจาะจงในการกรอกข้อมูล Spanning Tree
            # เช่น "Fa0/2:Root FWD" หรือ "Fa0/4:Altn BLK"
            
            spanning_tree_sw1 = {}
            for line in spanning_tree_sw1_text.strip().split('\n'):
                if line and ":" in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        port = parts[0].strip()
                        status = parts[1].strip()
                        spanning_tree_sw1[port] = status
            
            spanning_tree_sw2 = {}
            for line in spanning_tree_sw2_text.strip().split('\n'):
                if line and ":" in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        port = parts[0].strip()
                        status = parts[1].strip()
                        spanning_tree_sw2[port] = status
            
            spanning_tree_sw3 = {}
            for line in spanning_tree_sw3_text.strip().split('\n'):
                if line and ":" in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        port = parts[0].strip()
                        status = parts[1].strip()
                        spanning_tree_sw3[port] = status
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "switch3_keywords": switch3_keywords,
                    "spanning_tree_sw1": spanning_tree_sw1,
                    "spanning_tree_sw2": spanning_tree_sw2,
                    "spanning_tree_sw3": spanning_tree_sw3,
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
                }},
                upsert=True
            )

        elif lab_num == 5:
            # อัพเดทสำหรับ Lab 5
            switch1_keywords_text = request.form.get('switch1_keywords', '')
            switch2_keywords_text = request.form.get('switch2_keywords', '')
            switch3_keywords_text = request.form.get('switch3_keywords', '')
            pca_ip = request.form.get('pca_ip', '')
            pca_subnet = request.form.get('pca_subnet', '')
            pcc_ip = request.form.get('pcc_ip', '')
            pcc_subnet = request.form.get('pcc_subnet', '')
            
            # แปลงข้อความเป็นรายการคีย์เวิร์ด
            switch1_keywords = parse_keywords_from_text(switch1_keywords_text)
            switch2_keywords = parse_keywords_from_text(switch2_keywords_text)
            switch3_keywords = parse_keywords_from_text(switch3_keywords_text)
            
            # บันทึกลงฐานข้อมูล
            lab_keywords_collection.update_one(
                {"lab_num": lab_num},
                {"$set": {
                    "switch1_keywords": switch1_keywords,
                    "switch2_keywords": switch2_keywords,
                    "switch3_keywords": switch3_keywords,
                    "pca_config": {
                        "ip": pca_ip,
                        "subnet": pca_subnet
                    },
                    "pcc_config": {
                        "ip": pcc_ip,
                        "subnet": pcc_subnet
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
        
        # ลบการส่งงานทั้งหมดในแล็บนี้หรือไม่
        delete_submissions = request.form.get('delete_submissions', 'no')
        deleted_count = 0
        
        if delete_submissions == 'yes':
            delete_result = scores_collection.delete_many({"lab": f"Lab {lab_num}"})
            deleted_count = delete_result.deleted_count
            flash(f'อัพเดทคีย์เวิร์ดเรียบร้อยแล้ว และลบการส่งงาน {deleted_count} รายการ', 'success')
        else:
            flash('อัพเดทคีย์เวิร์ดเรียบร้อยแล้ว', 'success')
            
    except Exception as e:
        print(f"Error updating keywords: {str(e)}")
        flash(f'เกิดข้อผิดพลาดในการอัพเดทคีย์เวิร์ด: {str(e)}', 'danger')
    
    return redirect(url_for('teacher.lab_management', lab_num=lab_num))