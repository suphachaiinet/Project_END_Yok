from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_session import Session
import logging
from bson import ObjectId
from lab import lab_bp  # นำเข้า lab_bp จาก lab.py

app = Flask(__name__)

# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/yourdatabase'  # ปรับตาม MongoDB URI ของคุณ
app.secret_key = 'your_secret_key'  # กำหนด secret_key ที่เป็นความลับ

# ตั้งค่าการส่งอีเมล
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 's6506022410031@email.kmutnb.ac.th'  # ใช้อีเมลของคุณ
app.config['MAIL_PASSWORD'] = 'y053645033'  # ใช้รหัสแอปที่ได้
app.config['MAIL_DEFAULT_SENDER'] = 's6506022410031@email.kmutnb.ac.th'  # ตั้งค่า default sender
mail = Mail(app)

# ใช้ Flask-Session เพื่อจัดการเซสชัน
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# ตั้งค่าการบันทึกล็อกทั้งในไฟล์และแสดงใน terminal
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # สำหรับแสดงใน terminal
        logging.FileHandler('login_activity.log')  # สำหรับบันทึกในไฟล์
    ]
)

# สร้าง URL สำหรับการยืนยัน
def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(email, salt='email-confirm')

# ส่งอีเมลยืนยัน
def send_confirmation_email(user_email, token):
    confirm_url = url_for('confirm_email', token=token, _external=True)
    msg = Message('Please confirm your email', recipients=[user_email])
    msg.body = f'Your confirmation link is: {confirm_url}'
    try:
        mail.send(msg)
    except Exception as e:
        logging.error(f'Error sending email: {str(e)}')
        flash(f'ไม่สามารถส่งอีเมลได้: {str(e)}', 'danger')

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

        # สร้าง token และส่งอีเมลยืนยัน
        token = generate_confirmation_token(email)
        try:
            send_confirmation_email(email, token)
        except Exception as e:
            logging.error(f'Error sending email: {str(e)}')
            flash(f'ไม่สามารถส่งอีเมลได้: {str(e)}', 'danger')
            return redirect(url_for('register'))

        # เพิ่มข้อมูลผู้ใช้เฉพาะหลังจากยืนยันอีเมล
        session['pending_user'] = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
            "role": role
        }

        flash('สมัครสมาชิกสำเร็จ! โปรดยืนยันอีเมลของคุณเพื่อเปิดใช้งานบัญชี', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

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

        if not user['is_verified']:
            flash('กรุณายืนยันอีเมลของคุณก่อนเข้าสู่ระบบ', 'danger')
            return redirect(url_for('login'))

        # ตรวจสอบบทบาทและการย้ายข้อมูล
        role = user.get('role', 'user')
        if role == 'teacher':
            teacher_data = mongo.db.teachers.find_one({"user_id": str(user['_id'])})
            if not teacher_data:
                flash('ข้อมูลของคุณยังไม่ได้ถูกย้ายเข้าสู่ระบบสำหรับครู', 'danger')
                return redirect(url_for('login'))
        elif role == 'student':
            student_data = mongo.db.students.find_one({"user_id": str(user['_id'])})
            if not student_data:
                flash('ข้อมูลของคุณยังไม่ได้ถูกย้ายเข้าสู่ระบบสำหรับนักเรียน', 'danger')
                return redirect(url_for('login'))

        # บันทึก session
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role'] = role

        flash('เข้าสู่ระบบสำเร็จ!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))
    
    user = mongo.db.users_all.find_one({"_id": ObjectId(session['user_id'])})

    if user is None:
        flash('User not found in the database.', 'danger')
        return redirect(url_for('login'))

    role = session.get('role', 'user')
    if role == 'teacher':
        return render_template('teacher_dashboard.html', first_name=user['first_name'], last_name=user['last_name'])
    elif role == 'student':
        return render_template('student_dashboard.html', first_name=user['first_name'], last_name=user['last_name'])
    else:
        flash('Invalid role detected.', 'danger')
        return redirect(url_for('login'))

@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        # ยืนยัน Token และดึงอีเมล
        serializer = URLSafeTimedSerializer(app.secret_key)
        email = serializer.loads(token, salt='email-confirm', max_age=3600)  # หมดอายุภายใน 1 ชั่วโมง
    except:
        flash('ลิงก์ยืนยันหมดอายุหรือไม่ถูกต้อง', 'danger')
        return redirect(url_for('login'))

    # ค้นหาผู้ใช้ใน session ที่ยังไม่ยืนยัน
    pending_user = session.get('pending_user')
    if pending_user and pending_user.get('email') == email:
        # เพิ่มข้อมูลลงในฐานข้อมูล
        pending_user['is_verified'] = True
        mongo.db.users_all.insert_one(pending_user)

        # ย้ายข้อมูลไปยัง collection ตาม role
        role = pending_user['role']
        if role == 'teacher':
            mongo.db.teachers.insert_one({
                "user_id": str(pending_user['_id']),
                "first_name": pending_user['first_name'],
                "last_name": pending_user['last_name'],
                "email": pending_user['email']
            })
        elif role == 'student':
            mongo.db.students.insert_one({
                "user_id": str(pending_user['_id']),
                "first_name": pending_user['first_name'],
                "last_name": pending_user['last_name'],
                "email": pending_user['email']
            })

        session.pop('pending_user', None)  # ลบข้อมูลผู้ใช้ที่รอการยืนยัน
        flash('อีเมลของคุณได้รับการยืนยันแล้วและข้อมูลถูกเพิ่มในระบบเรียบร้อย', 'success')
        return redirect(url_for('login'))
    else:
        flash('ไม่พบข้อมูลผู้ใช้ที่รอการยืนยัน', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()  # ลบข้อมูลใน session
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# ลงทะเบียน Blueprint สำหรับ lab
app.register_blueprint(lab_bp)

if __name__ == '__main__':
    app.run(debug=True)
