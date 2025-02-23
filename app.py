from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from flask_session import Session
from datetime import datetime  # เพิ่มบรรทัดนี้
from bson import ObjectId
import logging
from lab import scores_collection

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


# ลงทะเบียน Blueprint สำหรับอาจารย์
# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/network_users'
app.secret_key = 'admin_123'

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
    role = session.get('role', 'user')

    if role == 'teacher':
        # คำนวณข้อมูลสถิติสำหรับอาจารย์
        total_students = mongo.db.students.count_documents({})
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
        
        # จำนวนนักศึกษาที่ส่งงานทั้งหมด
        completed_students = len(set(score['username'] for score in all_scores))
        completion_rate = (completed_students / total_students * 100) if total_students > 0 else 0
        
        # หาเวลาที่มีการส่งงานล่าสุด
        latest_submission = max([score.get('timestamp', datetime.min) for score in all_scores], default=None)
        
        return render_template('teacher_dashboard.html',
                            first_name=user['first_name'],
                            last_name=user['last_name'],
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
                            overall_score=overall_score)
    
    else:
        flash('Invalid role detected.', 'danger')
        return redirect(url_for('login'))
    
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
