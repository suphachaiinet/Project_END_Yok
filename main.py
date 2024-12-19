from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from pymongo import MongoClient
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# เชื่อมต่อ MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client["my_database"]
students_collection = db["students"]

# Config Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your_email_password'
mail = Mail(app)

# Token Serializer
s = URLSafeTimedSerializer(app.secret_key)

# Flask-Bcrypt for password hashing
bcrypt = Bcrypt(app)

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        # ตรวจสอบว่ามี email นี้อยู่ใน MongoDB หรือไม่
        if students_collection.find_one({"email": email}):
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))

        # เพิ่มข้อมูลนักศึกษาใน MongoDB
        students_collection.insert_one({
            "email": email,
            "password": password,
            "is_verified": False
        })

        # ส่งอีเมล์ยืนยัน
        token = s.dumps(email, salt='email-confirm')
        link = url_for('verify_email', token=token, _external=True)
        msg = Message('Confirm Your Email', sender='your_email@gmail.com', recipients=[email])
        msg.body = f'Click the link to verify your email: {link}'
        mail.send(msg)

        flash('Registration successful! Please check your email to verify your account.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/verify_email/<token>')
def verify_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)  # 1 hour expiration
    except SignatureExpired:
        return 'The token is expired!'

    user = students_collection.find_one({"email": email})
    if user:
        students_collection.update_one({"email": email}, {"$set": {"is_verified": True}})
        flash('Email verified successfully!', 'success')
        return redirect(url_for('login'))
    return 'Invalid token!'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = students_collection.find_one({"email": email})

        if not user or not bcrypt.check_password_hash(user['password'], password):
            flash('Invalid credentials!', 'danger')
            return redirect(url_for('login'))

        if not user['is_verified']:
            flash('Please verify your email before logging in.', 'warning')
            return redirect(url_for('login'))

        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    # ตัวอย่างการดึงข้อมูลนักศึกษาจาก MongoDB และแสดงผล
    students = students_collection.find()
    return render_template('dashboard.html', students=students)

if __name__ == '__main__':
    app.run(debug=True)
