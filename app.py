from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_session import Session
import logging
from bson import ObjectId
from lab import scores_collection  # เพิ่มบรรทัดนี้

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

# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/yourdatabase'
app.secret_key = 'your_secret_key'

# ตั้งค่าอีเมล (ถ้าจำเป็น)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 's6506022410031@email.kmutnb.ac.th'
app.config['MAIL_PASSWORD'] = 'y053645033'
app.config['MAIL_DEFAULT_SENDER'] = 's6506022410031@email.kmutnb.ac.th'
mail = Mail(app)

# ใช้ Flask-Session เพื่อจัดการเซสชัน
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SECRET_KEY'] = 'your_strong_secret_key_here'  # ใช้คีย์ที่ซับซ้อนและปลอดภัย
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

        # สร้าง token และส่งอีเมลยืนยัน (ถ้าต้องการระบบยืนยันอีเมล)
        token = generate_confirmation_token(email)
        try:
            send_confirmation_email(email, token)
        except Exception as e:
            logging.error(f'Error sending email: {str(e)}')
            flash(f'ไม่สามารถส่งอีเมลได้: {str(e)}', 'danger')
            return redirect(url_for('register'))

        # เก็บข้อมูลผู้ใช้ไว้ใน session ชั่วคราว
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

        # ถ้าคุณมีระบบยืนยันอีเมล
        if not user.get('is_verified'):
            flash('กรุณายืนยันอีเมลของคุณก่อนเข้าสู่ระบบ', 'danger')
            return redirect(url_for('login'))

        role = user.get('role', 'user')

        # ตรวจสอบว่ามีข้อมูลใน teachers/students หรือไม่
        if role == 'teacher':
            teacher_data = mongo.db.teachers.find_one({"username": user['username']})
            if not teacher_data:
                flash('ข้อมูลของคุณยังไม่ได้ถูกย้ายเข้าสู่ระบบสำหรับครู', 'danger')
                return redirect(url_for('login'))
        elif role == 'student':
            student_data = mongo.db.students.find_one({"username": user['username']})
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
    
    # Debug: พิมพ์ username
    print(f"Username: {user['username']}")
    
    # ดึงคะแนนแล็ปจาก MongoDB
    lab_scores = [0] * 16  # สำหรับ Lab 1-16
    
    # ค้นหาคะแนนสำหรับผู้ใช้งานปัจจุบัน
    user_lab_scores = list(scores_collection.find({"username": user['username']}))
    
    # Debug: พิมพ์คะแนนที่พบ
    print(f"Lab Scores found: {user_lab_scores}")
    
    for score_entry in user_lab_scores:
        try:
            lab_num = int(score_entry['lab'].replace('Lab ', '')) - 1
            score = float(score_entry['switch_score'].split('/')[0])
            lab_scores[lab_num] = score
            
            # Debug: พิมพ์คะแนนแต่ละแล็บ
            print(f"Lab {lab_num + 1} Score: {score}")
        except Exception as e:
            print(f"Error processing score: {e}")

    # คำนวณคะแนนรวม
    overall_score = sum(lab_scores) / 16

    if role == 'teacher':
        return render_template('teacher_dashboard.html',
                               first_name=user['first_name'],
                               last_name=user['last_name'])
    elif role == 'student':
        return render_template('student_dashboard.html',
                               first_name=user['first_name'],
                               last_name=user['last_name'],
                               scores=lab_scores,
                               overall_score=overall_score)
    else:
        flash('Invalid role detected.', 'danger')
        return redirect(url_for('login'))
    
@app.route('/confirm/<token>')
def confirm_email(token):
    try:
        serializer = URLSafeTimedSerializer(app.secret_key)
        email = serializer.loads(token, salt='email-confirm', max_age=3600)
    except:
        flash('ลิงก์ยืนยันหมดอายุหรือไม่ถูกต้อง', 'danger')
        return redirect(url_for('login'))

    pending_user = session.get('pending_user')
    if pending_user and pending_user.get('email') == email:
        # เพิ่มข้อมูลลงในฐานข้อมูล
        pending_user['is_verified'] = True
        mongo.db.users_all.insert_one(pending_user)

        # ย้ายข้อมูลตาม role (ใช้ username แทน user_id)
        role = pending_user['role']
        if role == 'teacher':
            mongo.db.teachers.insert_one({
                "username": pending_user['username'],
                "first_name": pending_user['first_name'],
                "last_name": pending_user['last_name'],
                "email": pending_user['email']
            })
        elif role == 'student':
            mongo.db.students.insert_one({
                "username": pending_user['username'],
                "first_name": pending_user['first_name'],
                "last_name": pending_user['last_name'],
                "email": pending_user['email']
            })

        session.pop('pending_user', None)
        flash('อีเมลของคุณได้รับการยืนยันแล้วและข้อมูลถูกเพิ่มในระบบเรียบร้อย', 'success')
        return redirect(url_for('login'))
    else:
        flash('ไม่พบข้อมูลผู้ใช้ที่รอการยืนยัน', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
