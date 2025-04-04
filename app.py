from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_session import Session
from datetime import datetime, timedelta  # เพิ่ม timedelta
from bson import ObjectId
import logging
from lab import scores_collection
from pdf_manager import pdf_bp
import time
import threading  # เพิ่ม threading

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

# นำเข้า Blueprint ของ Lab 1 และ Lab 2
from lab import lab_bp
from lab2 import lab2_bp
from lab3 import lab3_bp
from lab4 import lab4_bp
from lab5 import lab5_bp
from lab6 import lab6_bp
from lab7 import lab7_bp
from lab8 import lab8_bp
from lab9 import lab9_bp
from lab10 import lab10_bp
from lab11 import lab11_bp
from lab12 import lab12_bp
from lab13 import lab13_bp
from lab14 import lab14_bp
from lab15 import lab15_bp
from lab16 import lab16_bp
from teacher import teacher_bp
from admin import admin_bp  # เพิ่มบรรทัดนี้


app = Flask(__name__)
# ลงทะเบียน Blueprint สำหรับ lab ต่าง ๆ
app.register_blueprint(lab_bp, url_prefix='/lab')
app.register_blueprint(lab2_bp, url_prefix='/lab2')
app.register_blueprint(lab3_bp, url_prefix='/lab3')
app.register_blueprint(lab4_bp, url_prefix='/lab4')
app.register_blueprint(lab5_bp, url_prefix='/lab5')
app.register_blueprint(lab6_bp, url_prefix='/lab6')
app.register_blueprint(lab7_bp, url_prefix='/lab7')
app.register_blueprint(lab8_bp, url_prefix='/lab8')
app.register_blueprint(lab9_bp, url_prefix='/lab9')
app.register_blueprint(lab10_bp, url_prefix='/lab10')
app.register_blueprint(lab11_bp, url_prefix='/lab11')
app.register_blueprint(lab12_bp, url_prefix='/lab12')
app.register_blueprint(lab13_bp, url_prefix='/lab13')
app.register_blueprint(lab14_bp, url_prefix='/lab14')
app.register_blueprint(lab15_bp, url_prefix='/lab15')
app.register_blueprint(lab16_bp, url_prefix='/lab16')
app.register_blueprint(teacher_bp, url_prefix='/teacher')
app.register_blueprint(pdf_bp, url_prefix='/pdf')
app.register_blueprint(admin_bp, url_prefix='/admin')  # เพิ่มบรรทัดนี้

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
import os
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'pdfs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ลงทะเบียน Blueprint สำหรับอาจารย์
# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/network_users'
app.secret_key = 'admin_123'

# ตั้งค่าอีเมล (ถ้าจำเป็น)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 's6506022410031@email.kmutnb.ac.th'  # แก้เป็นอีเมลที่ใช้งานได้จริง
app.config['MAIL_PASSWORD'] = 'y053645033'  # รหัสผ่านแอพของ Gmail (ตัวอย่าง)
app.config['MAIL_DEFAULT_SENDER'] = 's6506022410031@email.kmutnb.ac.th'  # แก้เป็นอีเมลที่ใช้งานได้จริง
mail = Mail(app)

# ใช้ Flask-Session เพื่อจัดการเซสชัน
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SECRET_KEY'] = 'admin_123'  # ใช้คีย์ที่ซับซ้อนและปลอดภัย
Session(app)

mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# ตั้งค่าการบันทึกล็อก
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)

# สร้าง Token สำหรับยืนยันอีเมล (ถ้าคุณมีระบบยืนยันอีเมล)
def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(email, salt='email-confirm')

def send_confirmation_email(user_email, token):
    confirm_url = url_for('confirm_email', token=token, _external=True)
    msg = Message('กรุณายืนยันอีเมลของคุณ', recipients=[user_email])
    msg.body = f'คุณมีเวลา 10 นาทีในการยืนยันอีเมลของคุณ คลิกที่ลิงก์นี้เพื่อยืนยัน: {confirm_url}'
    try:
        mail.send(msg)
        logging.info(f'ส่งอีเมลยืนยันไปที่ {user_email} สำเร็จ')
    except Exception as e:
        logging.error(f'ข้อผิดพลาดในการส่งอีเมล: {str(e)}')
        # ไม่เรียก flash ที่นี่ เพราะจะทำให้เกิด exception ซ้อน exception
        return False
    return True

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    session.pop('_flashes', None)
    if request.method == 'POST':
        try:
            # ข้อมูลจากฟอร์ม
            username = request.form.get('username')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            role = request.form.get('role')

            # ตรวจสอบว่ามีการส่ง Ajax หรือไม่
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

            # ตรวจสอบข้อมูล
            if not all([username, first_name, last_name, email, password, confirm_password, role]):
                if is_ajax:
                    return jsonify({"error": "กรุณากรอกข้อมูลให้ครบทุกช่อง"}), 400
                flash('กรุณากรอกข้อมูลให้ครบทุกช่อง', 'danger')
                return redirect(url_for('register'))

            # ตรวจสอบรหัสผ่านตรงกัน
            if password != confirm_password:
                if is_ajax:
                    return jsonify({"error": "รหัสผ่านและยืนยันรหัสผ่านไม่ตรงกัน"}), 400
                flash('รหัสผ่านและยืนยันรหัสผ่านไม่ตรงกัน', 'danger')
                return redirect(url_for('register'))

            # ตรวจสอบความยาวของรหัสผ่าน
            if len(password) < 6:
                if is_ajax:
                    return jsonify({"error": "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"}), 400
                flash('รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร', 'danger')
                return redirect(url_for('register'))

            # ตรวจสอบรูปแบบอีเมล
            import re
            email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
            if not email_pattern.match(email):
                if is_ajax:
                    return jsonify({"error": "รูปแบบอีเมลไม่ถูกต้อง"}), 400
                flash('รูปแบบอีเมลไม่ถูกต้อง', 'danger')
                return redirect(url_for('register'))

            # ตรวจสอบชื่อผู้ใช้ซ้ำ
            existing_user = mongo.db.users_all.find_one({"username": username})
            if existing_user:
                if is_ajax:
                    return jsonify({"error": "ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!"}), 400
                flash('ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!', 'danger')
                return redirect(url_for('register'))

            # ตรวจสอบอีเมลซ้ำ
            existing_email = mongo.db.users_all.find_one({"email": email})
            if existing_email:
                if is_ajax:
                    return jsonify({"error": "อีเมลนี้ถูกใช้ไปแล้ว!"}), 400
                flash('อีเมลนี้ถูกใช้ไปแล้ว!', 'danger')
                return redirect(url_for('register'))

            # เข้ารหัสรหัสผ่าน
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            
            # เก็บข้อมูลผู้ใช้ลงในฐานข้อมูลทันที แต่ตั้งค่า is_verified เป็น False
            user_data = {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "password": hashed_password,
                "role": role,
                "is_verified": False,  # ต้องรอการยืนยันอีเมล
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # เพิ่มผู้ใช้ลงในฐานข้อมูล
            mongo.db.users_all.insert_one(user_data)
            
            # บันทึกล็อก
            logging.info(f"ผู้ใช้ใหม่ลงทะเบียน: {username} ({email}) เป็น {role}")
            
            # พยายามส่งอีเมลยืนยัน
            email_sent = False
            try:
                token = generate_confirmation_token(email)
                email_sent = send_confirmation_email(email, token)
                if email_sent:
                    if is_ajax:
                        return jsonify({
                            "success": True, 
                            "message": "ลงทะเบียนสำเร็จและส่งอีเมลยืนยันแล้ว",
                            "redirect": url_for('registration_success', email=email, email_sent=True)
                        })
                    flash('ส่งอีเมลยืนยันเรียบร้อยแล้ว กรุณาตรวจสอบกล่องจดหมายของคุณ', 'success')
                else:
                    if is_ajax:
                        return jsonify({
                            "success": True, 
                            "warning": "ไม่สามารถส่งอีเมลยืนยันได้ในขณะนี้ แต่คุณสามารถเข้าสู่ระบบได้",
                            "redirect": url_for('registration_success', email=email, email_sent=False)
                        })
                    flash('ไม่สามารถส่งอีเมลยืนยันได้ในขณะนี้ แต่คุณสามารถเข้าสู่ระบบได้', 'warning')
            except Exception as e:
                logging.error(f'Error sending email: {str(e)}')
                if is_ajax:
                    return jsonify({
                        "success": True, 
                        "warning": "ไม่สามารถส่งอีเมลยืนยันได้ในขณะนี้ แต่คุณสามารถเข้าสู่ระบบได้",
                        "redirect": url_for('registration_success', email=email, email_sent=False)
                    })
                flash('ไม่สามารถส่งอีเมลยืนยันได้ในขณะนี้ แต่คุณสามารถเข้าสู่ระบบได้', 'warning')
            
            # แสดงหน้ายืนยันการลงทะเบียนสำเร็จ
            if not is_ajax:
                return render_template('registration_success.html', email=email, email_sent=email_sent)
            
            # สำหรับการร้องขอ Ajax ที่ไม่ได้ตอบกลับข้างต้น
            return jsonify({
                "success": True, 
                "redirect": url_for('registration_success') + f"?email={email}&email_sent={str(email_sent)}"
            })
            
        except Exception as e:
            # บันทึกข้อผิดพลาด
            logging.error(f"ข้อผิดพลาดในการลงทะเบียน: {str(e)}")
            
            # ตอบกลับตามประเภทของคำขอ
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"error": f"เกิดข้อผิดพลาด: {str(e)}"}), 500
            
            # แสดงข้อความแจ้งเตือน
            flash(f'เกิดข้อผิดพลาดในการลงทะเบียน: {str(e)}', 'danger')
            return redirect(url_for('register'))
        
    return render_template('register.html')

@app.route('/registration_success')
def registration_success():
    email = request.args.get('email', '')
    email_sent = request.args.get('email_sent', 'False') == 'True'
    return render_template('registration_success.html', email=email, email_sent=email_sent)

@app.route('/dashboard-student2')
def dashboard_student2():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get user data
    user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})
    
    # Get student scores
    username = session.get('username')
    user_scores = list(scores_collection.find({"username": username}))
    
    # Create score list for all labs
    lab_scores = [0] * 16
    
    # Fill in scores from database
    for score in user_scores:
        try:
            lab_num = int(score['lab'].replace('Lab ', '')) - 1
            score_value = float(score['switch_score'].split('/')[0])
            lab_scores[lab_num] = score_value
        except Exception as e:
            print(f"Error processing score: {e}")
    
    # Calculate overall score
    overall_score = sum(lab_scores) / len(lab_scores) if lab_scores else 0
    
    # Count completed labs (important fix)
    completed_labs = sum(1 for score in lab_scores if score == 100)
    
    # Current time for last activity
    last_lab_time = datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    
    # Lab titles
    lab_titles = [
        "Basic Switch Configuration",
        "Configure VLANs and Trunking",
        "Implement VLANs and Trunking",
        "Redundant Links",
        "Rapid PVST+",
        "Router-on-a-Stick Inter-VLAN",
        "Inter-VLAN Routing",
        "EtherChannel",
        "PPP Authentication",
        "Standard IPv4 ACLs",
        "Extended IPv4 ACLs",
        "DHCPv4",
        "DHCPv6",
        "NAT",
        "HSRP",
        "Switch Security"
    ]
    
    # Lab endpoints mapping
    lab_endpoints = {
        1: 'lab.lab1',
        2: 'lab2.lab2',
        3: 'lab3.lab3',
        4: 'lab4.lab4',
        5: 'lab5.lab5',
        6: 'lab6.lab6',
        7: 'lab7.lab7',
        8: 'lab8.lab8',
        9: 'lab9.lab9',
        10: 'lab10.lab10',
        11: 'lab11.lab11',
        12: 'lab12.lab12',
        13: 'lab13.lab13',
        14: 'lab14.lab14',
        15: 'lab15.lab15',
        16: 'lab16.lab16'
    }
    
    return render_template(
        'dashboard_student2.html',
        first_name=user['first_name'],
        last_name=user['last_name'],
        scores=lab_scores,
        overall_score=overall_score,
        average_score=overall_score,
        last_lab_time=last_lab_time,
        lab_titles=lab_titles,
        active_lab=None,
         completed_labs=completed_labs,
        lab_endpoints=lab_endpoints
    )
@app.route('/confirm_email/<token>')
def confirm_email(token):
    try:
        serializer = URLSafeTimedSerializer(app.secret_key)
        email = serializer.loads(token, salt='email-confirm', max_age=600)  # 600 วินาที = 10 นาที
    except:
        flash('ลิงก์ยืนยันไม่ถูกต้องหรือหมดอายุแล้ว', 'danger')
        return redirect(url_for('login'))
    
    # หาผู้ใช้โดยใช้อีเมล
    user = mongo.db.users_all.find_one({"email": email})
    
    if not user:
        flash('ไม่พบบัญชีผู้ใช้', 'danger')
        return redirect(url_for('login'))
    
    if user.get('is_verified', False):
        flash('บัญชีนี้ได้รับการยืนยันแล้ว โปรดเข้าสู่ระบบ', 'info')
        return redirect(url_for('login'))
    
    # อัปเดตสถานะการยืนยัน
    mongo.db.users_all.update_one(
        {"email": email},
        {"$set": {"is_verified": True}}
    )
    
    # ตรวจสอบและเพิ่มข้อมูลในคอลเล็กชันของ students หรือ teachers
    if user['role'] == 'student':
        # ตรวจสอบว่ามีข้อมูลในคอลเล็กชัน students หรือไม่
        student = mongo.db.students.find_one({"username": user['username']})
        if not student:
            # ถ้าไม่มี ให้เพิ่มข้อมูลใหม่
            mongo.db.students.insert_one({
                "username": user['username'],
                "first_name": user['first_name'],
                "last_name": user['last_name'],
                "email": user['email'],
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            })
    
    flash('บัญชีของคุณได้รับการยืนยันเรียบร้อยแล้ว คุณสามารถเข้าสู่ระบบได้ทันที', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            user = mongo.db.users_all.find_one({"username": username})

            if not user:
                flash('ชื่อผู้ใช้งานไม่ถูกต้อง!', 'danger')
                return redirect(url_for('login'))
            
            try:
                # ตรวจสอบรหัสผ่าน
                if not bcrypt.check_password_hash(user['password'], password):
                    flash('รหัสผ่านไม่ถูกต้อง!', 'danger')
                    return redirect(url_for('login'))
            except ValueError:
                # กรณีเกิดปัญหากับรหัสผ่านเก่า
                logging.error(f"Invalid password hash for user {username}")
                
                # สร้างรหัสผ่านใหม่
                new_hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
                
                # อัปเดตรหัสผ่านใหม่
                mongo.db.users_all.update_one(
                    {"username": username},
                    {"$set": {"password": new_hashed_password}}
                )
                
                flash('รหัสผ่านถูกรีเซ็ตโดยอัตโนมัติ กรุณาเข้าสู่ระบบอีกครั้ง', 'warning')
                return redirect(url_for('login'))

            role = user.get('role', 'user')
            
            # บันทึกเวลาเข้าสู่ระบบล่าสุด
            mongo.db.users_all.update_one(
                {"_id": ObjectId(user['_id'])},
                {"$set": {"last_login": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")}} 
            )

            # บันทึกกิจกรรมการเข้าสู่ระบบ
            activity_log = {
                "user_id": str(user['_id']),
                "username": user['username'],
                "action": "login",
                "ip_address": request.remote_addr,
                "timestamp": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            }
            mongo.db.activity_logs.insert_one(activity_log)

            # เพิ่มเงื่อนไขสำหรับแอดมิน
            if role == 'admin':
                # บันทึก session
                session['user_id'] = str(user['_id'])
                session['username'] = user['username']
                session['role'] = role
                session['first_name'] = user.get('first_name', '')
                session['last_name'] = user.get('last_name', '')
                
                logging.info(f"Admin login: {user['username']}")
                flash('เข้าสู่ระบบสำเร็จ!', 'success')
                return redirect(url_for('admin.dashboard'))  # แก้เป็น admin.dashboard

            # ตรวจสอบว่ามีข้อมูลใน teachers/students หรือไม่
            if role == 'teacher':
                # ถ้าเป็นอาจารย์ต้องตรวจสอบการอนุมัติด้วย
                if not user.get('is_approved', False):
                    flash('บัญชีของคุณยังรอการอนุมัติจากแอดมิน', 'warning')
                    return redirect(url_for('login'))
                    
                teacher_data = mongo.db.teachers.find_one({"username": user['username']})
                if not teacher_data:
                    flash('ข้อมูลของคุณยังไม่ได้ถูกย้ายเข้าสู่ระบบสำหรับครู', 'danger')
                    return redirect(url_for('login'))
            elif role == 'student':
                student_data = mongo.db.students.find_one({"username": user['username']})
                if not student_data:
                    # หากไม่มีข้อมูลนักศึกษา ให้สร้างข้อมูลอัตโนมัติ
                    student_data = {
                        "username": user['username'],
                        "first_name": user['first_name'],
                        "last_name": user['last_name'],
                        "email": user['email'],
                        "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                    }
                    mongo.db.students.insert_one(student_data)

            # บันทึก session
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = role
            session['first_name'] = user.get('first_name', '')
            session['last_name'] = user.get('last_name', '')

            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('dashboard'))

        except Exception as e:
            logging.error(f"Login error: {e}")
            flash('เกิดข้อผิดพลาดในการเข้าสู่ระบบ', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')
    
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('กรุณาเข้าสู่ระบบ', 'danger')
        return redirect(url_for('login'))
    
    user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})
    # ใช้ temp_role ถ้ามี (สำหรับแอดมินที่สลับบทบาท) หรือใช้ role ปกติ
    role = session.get('temp_role', session.get('role', 'user'))
    lab_titles = [
        "Basic Switch Configuration",
        "Configure VLANs and Trunking",
        "Implement VLANs and Trunking",
        "Redundant Links",
        "Rapid PVST+",
        "Router-on-a-Stick Inter-VLAN",
        "Inter-VLAN Routing",
        "EtherChannel",
        "PPP Authentication",
        "Standard IPv4 ACLs",
        "Extended IPv4 ACLs",
        "DHCPv4",
        "DHCPv6",
        "NAT",
        "HSRP",
        "Switch Security"
    ]

    # เปลี่ยนเส้นทางสำหรับแอดมิน
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'teacher':
        # คำนวณข้อมูลสถิติสำหรับอาจารย์
        all_scores = list(scores_collection.find())
        
        # คำนวณคะแนนเฉลี่ย
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
        total_students = mongo.db.students.count_documents({})
        
        # จำนวนนักศึกษาที่ส่งงานทั้งหมด
        completed_students = len(set(score['username'] for score in all_scores))
        completion_rate = (completed_students / total_students * 100) if total_students > 0 else 0
        
        # หาเวลาที่มีการส่งงานล่าสุด
        latest_submission = max([score.get('timestamp', datetime.min).replace(microsecond=0) for score in all_scores], default=None)
        
        return render_template('teacher_dashboard.html',
                           first_name=user.get('first_name', 'Unknown'),
                           last_name=user.get('last_name', 'User'),
                           total_students=total_students,
                           avg_score=avg_score,
                           completion_rate=completion_rate,
                           lab_titles=lab_titles,
                           last_activity_time=latest_submission)
    
    elif role == 'student':
        # ดึงคะแนนของนักศึกษา
        username = session.get('username')
        user_scores = list(scores_collection.find({"username": username}))
        
        # สร้างรายการคะแนนสำหรับแต่ละแล็บ
        lab_scores = [0] * 16  # สร้างรายการคะแนนว่างสำหรับ 16 แล็บ
        
        # ใส่คะแนนที่มีอยู่
        for score in user_scores:
            try:
                lab_num = int(score['lab'].replace('Lab ', '')) - 1  # ลบ 1 เพราะ index เริ่มที่ 0
                score_value = float(score['switch_score'].split('/')[0])
                lab_scores[lab_num] = score_value
            except Exception as e:
                print(f"Error processing score: {e}")
        
        # คำนวณคะแนนรวม
        overall_score = sum(lab_scores) / len(lab_scores) if lab_scores else 0
        
        # เพิ่มการกำหนดค่า last_lab_time
        last_lab_time = datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        
        return render_template('dashboard_student2.html',
                      first_name=user['first_name'],
                      last_name=user['last_name'],
                      scores=lab_scores,
                      overall_score=overall_score,
                      active_lab=None,
                      lab_titles=lab_titles,
                      last_lab_time=last_lab_time)  # เพิ่มบรรทัดนี้
    
    else:
        flash('Invalid role detected.', 'danger')
        return redirect(url_for('login'))
    
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# สร้างฟังก์ชันสำหรับสร้างผู้ใช้แอดมินเริ่มต้น (ไม่มี decorator)
def create_admin_user():
    # ตรวจสอบว่ามีผู้ใช้แอดมินอยู่แล้วหรือไม่
    admin_user = mongo.db.users_all.find_one({"username": "admin"})
    
    if not admin_user:
        # สร้างรหัสผ่านแบบแฮช
        hashed_password = bcrypt.generate_password_hash("P@ssw0rd").decode('utf-8')
        
        # สร้างผู้ใช้แอดมินใหม่
        admin = {
            "username": "admin",
            "password": hashed_password,
            "first_name": "admin",
            "last_name": "admin",
            "email": "suphachai10978@gmail.com",
            "role": "admin",
            "is_verified": True,
            "is_approved": True,
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # เพิ่มลงในฐานข้อมูล
        mongo.db.users_all.insert_one(admin)
        
        print("* สร้างผู้ใช้แอดมินเรียบร้อยแล้ว *")
    else:
        # หากมีผู้ใช้แอดมินอยู่แล้ว ให้ลองอัปเดตรหัสผ่าน
        try:
            # ตรวจสอบและเพิ่ม created_at หากยังไม่มี
            if 'created_at' not in admin_user:
                mongo.db.users_all.update_one(
                    {"username": "admin"},
                    {"$set": {
                        "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                    }}
                )
            
            new_hashed_password = bcrypt.generate_password_hash("P@ssw0rd").decode('utf-8')
            mongo.db.users_all.update_one(
                {"username": "admin"},
                {"$set": {
                    "password": new_hashed_password,
                    "is_verified": True,
                    "is_approved": True
                }}
            )
            print("* อัปเดตรหัสผ่านแอดมินเรียบร้อยแล้ว *")
        except Exception as e:
            print(f"* เกิดข้อผิดพลาดในการอัปเดตรหัสผ่าน: {e} *")

# ฟังก์ชันสำหรับตรวจสอบและลบผู้ใช้ที่ไม่ยืนยันอีเมล
def cleanup_unverified_users():
    while True:
        try:
            # คำนวณเวลาที่ผ่านมาแล้ว 10 นาที
            cutoff_time = datetime.now(ZoneInfo("Asia/Bangkok")) - timedelta(minutes=10)
            cutoff_time_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # ค้นหาผู้ใช้ที่ไม่ยืนยันและสร้างมานานกว่า 10 นาที
            unverified_users = list(mongo.db.users_all.find({
                "is_verified": False,
                "created_at": {"$lt": cutoff_time_str}
            }))
            
            # ลบผู้ใช้ที่ไม่ยืนยันแต่ละคน
            count = 0
            for user in unverified_users:
                username = user.get('username')
                email = user.get('email')
                
                # ลบผู้ใช้จากคอลเลคชัน users_all
                mongo.db.users_all.delete_one({"_id": user['_id']})
                
                # บันทึกล็อก
                logging.info(f"ลบผู้ใช้ที่ไม่ยืนยันอีเมล: {username} ({email})")
                count += 1
            
            if count > 0:
                logging.info(f"ลบผู้ใช้ที่ไม่ยืนยันอีเมลทั้งหมด {count} คน")
            
            # รอ 1 นาทีก่อนการตรวจสอบครั้งถัดไป
            time.sleep(60)
        except Exception as e:
            logging.error(f"เกิดข้อผิดพลาดในการลบผู้ใช้ที่ไม่ยืนยัน: {str(e)}")
            time.sleep(60)  # หากมีข้อผิดพลาด ให้รอก่อนลองใหม่

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # ตรวจสอบรหัสผ่านใหม่ตรงกัน
        if new_password != confirm_password:
            flash('รหัสผ่านใหม่ไม่ตรงกัน', 'danger')
            return redirect(url_for('change_password'))
        
        # ตรวจสอบความยาวของรหัสผ่าน
        if len(new_password) < 6:
            flash('รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 6 ตัวอักษร', 'danger')
            return redirect(url_for('change_password'))
        
        # ดึงข้อมูลผู้ใช้
        user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            flash('ไม่พบข้อมูลผู้ใช้', 'danger')
            return redirect(url_for('logout'))
        
        # ตรวจสอบรหัสผ่านปัจจุบัน
        if not bcrypt.check_password_hash(user['password'], current_password):
            flash('รหัสผ่านปัจจุบันไม่ถูกต้อง', 'danger')
            return redirect(url_for('change_password'))
        
        # เข้ารหัสพาสเวิร์ดใหม่
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # อัปเดตรหัสผ่านในฐานข้อมูล
        mongo.db.users_all.update_one(
            {"_id": ObjectId(session['user_id'])},
            {"$set": {"password": hashed_password, "password_updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
                      }}
        )
        
        flash('เปลี่ยนรหัสผ่านสำเร็จ', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')


@app.route('/student/change_password', methods=['GET', 'POST'])
def student_change_password():
    if 'user_id' not in session or session.get('role') != 'student':
        flash('กรุณาเข้าสู่ระบบก่อน', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # ตรวจสอบรหัสผ่านใหม่ตรงกัน
        if new_password != confirm_password:
            flash('รหัสผ่านใหม่ไม่ตรงกัน', 'danger')
            return redirect(url_for('student_change_password'))
        
        # ตรวจสอบความยาวของรหัสผ่าน
        if len(new_password) < 6:
            flash('รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 6 ตัวอักษร', 'danger')
            return redirect(url_for('student_change_password'))
        
        # ดึงข้อมูลผู้ใช้
        user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            flash('ไม่พบข้อมูลผู้ใช้', 'danger')
            return redirect(url_for('logout'))
        
        # ตรวจสอบรหัสผ่านปัจจุบัน
        if not bcrypt.check_password_hash(user['password'], current_password):
            flash('รหัสผ่านปัจจุบันไม่ถูกต้อง', 'danger')
            return redirect(url_for('student_change_password'))
        
        # เข้ารหัสพาสเวิร์ดใหม่
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        # อัปเดตรหัสผ่านในฐานข้อมูล
        mongo.db.users_all.update_one(
            {"_id": ObjectId(session['user_id'])},
            {"$set": {
                "password": hashed_password, 
                "password_updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            }}
        )
        
        flash('เปลี่ยนรหัสผ่านสำเร็จ', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('student_change_password.html')


if __name__ == '__main__':
    with app.app_context():
        create_admin_user()
        
    # เริ่มเธรดสำหรับลบผู้ใช้ที่ไม่ยืนยัน
    cleanup_thread = threading.Thread(target=cleanup_unverified_users, daemon=True)
    cleanup_thread.start()
    
    app.run(host='0.0.0.0', port=5000 ,debug=True) 
