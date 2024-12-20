from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_session import Session
from datetime import datetime
import logging
from bson import ObjectId

app = Flask(__name__)

# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/yourdatabase'  # ปรับตาม MongoDB URI ของคุณ
app.secret_key = 'your_secret_key'  # กำหนด secret_key ที่เป็นความลับ

# ตั้งค่าการส่งอีเมล
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'  # ใช้อีเมลของคุณ
app.config['MAIL_PASSWORD'] = 'your_app_password'  # ใช้รหัสแอปที่ได้
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
    mail.send(msg)

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

        new_user = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
            "role": role,
            "is_verified": False  # ตั้งค่าเป็น False จนกว่าจะยืนยันอีเมล
        }

        result = mongo.db.users_all.insert_one(new_user)
        if result.inserted_id:
            # สร้าง token และส่งอีเมลยืนยัน
            token = generate_confirmation_token(email)
            try:
                send_confirmation_email(email, token)
                flash('สมัครสมาชิกสำเร็จ! โปรดยืนยันอีเมลของคุณ', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'ไม่สามารถส่งอีเมลได้: {str(e)}', 'danger')
                return redirect(url_for('register'))
        else:
            flash('เกิดข้อผิดพลาดในการสมัคร โปรดลองใหม่อีกครั้ง', 'danger')
            return redirect(url_for('register'))
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

        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role'] = user['role']  # เก็บบทบาทผู้ใช้ใน session
        
        flash('Login successful!', 'success')
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
        serializer = URLSafeTimedSerializer(app.secret_key)
        email = serializer.loads(token, salt='email-confirm', max_age=3600)  # ตั้งเวลาให้ลิงก์หมดอายุหลัง 1 ชั่วโมง
    except:
        flash('ลิงก์ยืนยันหมดอายุหรือไม่ถูกต้อง', 'danger')
        return redirect(url_for('login'))

    # อัปเดตสถานะ is_verified เป็น True
    user = mongo.db.users_all.find_one({"email": email})
    if user:
        mongo.db.users_all.update_one(
            {"email": email},
            {"$set": {"is_verified": True}}
        )
        flash('อีเมลของคุณได้รับการยืนยันแล้ว', 'success')
        return redirect(url_for('login'))
    else:
        flash('ผู้ใช้ไม่พบ', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()  # ลบข้อมูลใน session
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
