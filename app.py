from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from bson import ObjectId

app = Flask(__name__)

# ตั้งค่า URI ของ MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/yourdatabase'  # ปรับตาม MongoDB URI ของคุณ
app.secret_key = 'your_secret_key'  # กำหนด secret_key ที่เป็นความลับ

mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# หน้าลงทะเบียน
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        
        # ตรวจสอบว่าอีเมลมีในระบบหรือไม่
        existing_user = mongo.db.users.find_one({"email": email})
        if existing_user:
            flash('Email is already registered!', 'danger')
            return redirect(url_for('register'))
        
        # สร้างผู้ใช้ใหม่ใน MongoDB
        new_user = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "password": password,
            "is_verified": False
        }

        try:
            mongo.db.users.insert_one(new_user)
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error occurred while registering: {e}")
            flash('Error occurred while registering. Please try again.', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

# หน้า Verify Email
@app.route('/verify_email/<token>')
def verify_email(token):
    # ต้องใช้การยืนยัน token ด้วยวิธีที่เหมาะสม เช่น JWT หรือการสร้าง token ด้วยการเข้ารหัส
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        return 'The token is expired!'

    user = mongo.db.users.find_one({"email": email})
    if user:
        mongo.db.users.update_one({"_id": ObjectId(user['_id'])}, {"$set": {"is_verified": True}})
        flash('Email verified successfully!', 'success')
        return redirect(url_for('login'))
    return 'Invalid token!'

# หน้า Login g
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = mongo.db.users.find_one({"email": email})

        if not user or not bcrypt.check_password_hash(user['password'], password):
            flash('Invalid credentials!', 'danger')
            return redirect(url_for('login'))

        if not user['is_verified']:
            flash('Please verify your email before logging in.', 'warning')
            return redirect(url_for('login'))

        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

# หน้า Dashboard
@app.route('/dashboard')
def dashboard():
    return 'Welcome to your dashboard!'

if __name__ == '__main__':
    app.run(debug=True)
