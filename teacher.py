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
    
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    return render_template('teacher_stats.html', 
                          labs_data=labs_data,
                          first_name=first_name,
                          last_name=last_name)

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
                         switch_keywords=lab_keywords.get('switch_keywords', []),
                         switch1_keywords=lab_keywords.get('switch1_keywords', []),
                         switch2_keywords=lab_keywords.get('switch2_keywords', []),
                         general_keywords=lab_keywords.get('general_keywords', []),
                         pc_config=lab_keywords.get('pc_config', {}),
                         pc1_config=lab_keywords.get('pc1_config', {}),
                         pc2_config=lab_keywords.get('pc2_config', {}),
                         active_lab=lab_num,
                         first_name=first_name,
                         last_name=last_name)

# อัพเดทคีย์เวิร์ด
@teacher_bp.route('/lab/<int:lab_num>/update', methods=['POST'])
def update_keywords(lab_num):
    if 'user_id' not in session or session.get('role') != 'teacher':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if lab_num == 1:
        # อัพเดทสำหรับ Lab 1
        switch_keywords_text = request.form.get('switch_keywords', '')
        pc_ip = request.form.get('pc_ip', '')
        pc_subnet = request.form.get('pc_subnet', '')
        pc_gateway = request.form.get('pc_gateway', '')
        
        # แปลงข้อความเป็นรายการคีย์เวิร์ด
        switch_keywords = []
        for line in switch_keywords_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('interface'):
                # เริ่มต้นบล็อก interface ใหม่
                current_interface = line
                interface_commands = []
                switch_keywords.append({current_interface: interface_commands})
            elif line.startswith(' ') and switch_keywords and isinstance(switch_keywords[-1], dict):
                # คำสั่งในบล็อก interface
                interface_commands = list(switch_keywords[-1].values())[0]
                interface_commands.append(line.strip())
            else:
                # คีย์เวิร์ดปกติ
                switch_keywords.append(line)
        
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
        switch1_keywords = []
        for line in switch1_keywords_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('interface'):
                # เริ่มต้นบล็อก interface ใหม่
                current_interface = line
                interface_commands = []
                switch1_keywords.append({current_interface: interface_commands})
            elif line.startswith(' ') and switch1_keywords and isinstance(switch1_keywords[-1], dict):
                # คำสั่งในบล็อก interface
                interface_commands = list(switch1_keywords[-1].values())[0]
                interface_commands.append(line.strip())
            else:
                # คีย์เวิร์ดปกติ
                switch1_keywords.append(line)
        
        switch2_keywords = []
        for line in switch2_keywords_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('interface'):
                # เริ่มต้นบล็อก interface ใหม่
                current_interface = line
                interface_commands = []
                switch2_keywords.append({current_interface: interface_commands})
            elif line.startswith(' ') and switch2_keywords and isinstance(switch2_keywords[-1], dict):
                # คำสั่งในบล็อก interface
                interface_commands = list(switch2_keywords[-1].values())[0]
                interface_commands.append(line.strip())
            else:
                # คีย์เวิร์ดปกติ
                switch2_keywords.append(line)
        
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
    else:
        # อัพเดทสำหรับแล็บอื่นๆ
        general_keywords_text = request.form.get('general_keywords', '')
        
        # แปลงข้อความเป็นรายการคีย์เวิร์ด
        try:
            # พยายามแปลงเป็น JSON ก่อน
            general_keywords = json.loads(general_keywords_text)
        except json.JSONDecodeError:
            # ถ้าไม่ใช่ JSON ให้แปลงเป็นรายการคีย์เวิร์ดแบบปกติ
            general_keywords = []
            for line in general_keywords_text.strip().split('\n'):
                line = line.strip()
                if line:
                    general_keywords.append(line)
        
        # บันทึกลงฐานข้อมูล
        lab_keywords_collection.update_one(
            {"lab_num": lab_num},
            {"$set": {
                "general_keywords": general_keywords,
                "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            }},
            upsert=True
        )
    
    flash('อัพเดทคีย์เวิร์ดเรียบร้อยแล้ว', 'success')
    return redirect(url_for('teacher.lab_management', lab_num=lab_num))

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