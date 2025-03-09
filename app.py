from flask import Flask, render_template, request, redirect, url_for, flash, session
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
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('login_activity.log')
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
        flash(f'ไม่สามารถส่งอีเมลได้: {str(e)}', 'danger')
        raise e

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        role = request.form['role']

        # ตรวจสอบชื่อผู้ใช้ซ้ำ
        existing_user = mongo.db.users_all.find_one({"username": username})
        if existing_user:
            flash('ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!', 'danger')
            return redirect(url_for('register'))

        # ตรวจสอบอีเมลซ้ำ
        existing_email = mongo.db.users_all.find_one({"email": email})
        if existing_email:
            flash('อีเมลนี้ถูกใช้ไปแล้ว!', 'danger')
            return redirect(url_for('register'))

        # เก็บข้อมูลผู้ใช้ลงในฐานข้อมูลทันที แต่ตั้งค่า is_verified เป็น False
        user_data = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
            "role": role,
            "is_verified": False,  # ต้องรอการยืนยันอีเมล
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }
        
        # เพิ่มผู้ใช้ลงในฐานข้อมูล
        mongo.db.users_all.insert_one(user_data)
        
        # พยายามส่งอีเมลยืนยัน แต่ถ้ามีปัญหา ให้แสดงหน้าสำเร็จโดยไม่ต้องรอ
        email_sent = False
        try:
            token = generate_confirmation_token(email)
            send_confirmation_email(email, token)
            email_sent = True
            flash('ส่งอีเมลยืนยันเรียบร้อยแล้ว กรุณาตรวจสอบกล่องจดหมายของคุณ', 'success')
        except Exception as e:
            logging.error(f'Error sending email: {str(e)}')
            flash('ไม่สามารถส่งอีเมลยืนยันได้ในขณะนี้ แต่คุณสามารถเข้าสู่ระบบได้', 'warning')
        
        # แสดงหน้ายืนยันการลงทะเบียนสำเร็จแทนการเปลี่ยนเส้นทาง
        return render_template('registration_success.html', email=email, email_sent=email_sent)
        
    return render_template('register.html')

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
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            })
    
    flash('บัญชีของคุณได้รับการยืนยันเรียบร้อยแล้ว คุณสามารถเข้าสู่ระบบได้ทันที', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = mongo.db.users_all.find_one({"username": username})

        if not user:
            flash('ชื่อผู้ใช้งานไม่ถูกต้อง!', 'danger')
            return redirect(url_for('login'))
        
        if not bcrypt.check_password_hash(user['password'], password):
            flash('รหัสผ่านไม่ถูกต้อง!', 'danger')
            return redirect(url_for('login'))

        # ถ้าคุณมีระบบยืนยันอีเมล
        if not user.get('is_verified', False):
            flash('กรุณายืนยันอีเมลของคุณก่อนเข้าสู่ระบบ', 'danger')
            return redirect(url_for('login'))

        role = user.get('role', 'user')
        # บันทึกเวลาเข้าสู่ระบบล่าสุด
        mongo.db.users_all.update_one(
            {"_id": ObjectId(user['_id'])},
            {"$set": {"last_login": datetime.now(ZoneInfo("Asia/Bangkok"))}}
        )

        # บันทึกกิจกรรมการเข้าสู่ระบบ (ถ้าต้องการระบบ Activity Log)
        activity_log = {
            "user_id": str(user['_id']),
            "username": user['username'],
            "action": "login",
            "ip_address": request.remote_addr,
            "timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))
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

            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('dashboard'))

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
                    "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
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
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))
    
    user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})
    # ใช้ temp_role ถ้ามี (สำหรับแอดมินที่สลับบทบาท) หรือใช้ role ปกติ
    role = session.get('temp_role', session.get('role', 'user'))

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
        latest_submission = max([score.get('timestamp', datetime.min) for score in all_scores], default=None)
        
        return render_template('teacher_dashboard.html',
                           first_name=user.get('first_name', 'Unknown'),
                           last_name=user.get('last_name', 'User'),
                           total_students=total_students,
                           avg_score=avg_score,
                           completion_rate=completion_rate,
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
        
        return render_template('student_dashboard.html',
                            first_name=user['first_name'],
                            last_name=user['last_name'],
                            scores=lab_scores,
                            overall_score=overall_score,
                            active_lab=None)
    
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
            "email": "suphachai10978@gmail.com",  # แก้ไขเป็นอีเมลที่ใช้งานได้
            "role": "admin",
            "is_verified": True,
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }
        
        # เพิ่มลงในฐานข้อมูล
        mongo.db.users_all.insert_one(admin)
        
        print("* สร้างผู้ใช้แอดมินเรียบร้อยแล้ว *")
    else:
        print("* ผู้ใช้แอดมินมีอยู่แล้ว *")

# ฟังก์ชันสำหรับตรวจสอบและลบผู้ใช้ที่ไม่ยืนยันอีเมล
def cleanup_unverified_users():
    while True:
        try:
            # คำนวณเวลาที่ผ่านมาแล้ว 10 นาที
            cutoff_time = datetime.now(ZoneInfo("Asia/Bangkok")) - timedelta(minutes=10)
            
            # ค้นหาผู้ใช้ที่ไม่ยืนยันและสร้างมานานกว่า 10 นาที
            unverified_users = list(mongo.db.users_all.find({
                "is_verified": False,
                "created_at": {"$lt": cutoff_time}
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
            {"$set": {"password": hashed_password, "password_updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))}}
        )
        
        flash('เปลี่ยนรหัสผ่านสำเร็จ', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html')

if __name__ == '__main__':
    with app.app_context():
        create_admin_user()
        
    # เริ่มเธรดสำหรับลบผู้ใช้ที่ไม่ยืนยัน
    cleanup_thread = threading.Thread(target=cleanup_unverified_users, daemon=True)
    cleanup_thread.start()
    
    app.run(debug=True)