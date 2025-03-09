from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from bson import ObjectId
import json

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

admin_bp = Blueprint('admin', __name__)

# เชื่อมต่อกับ MongoDB
from pymongo import MongoClient

mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']
users_collection = db['users_all']
teachers_collection = db['teachers']
students_collection = db['students']

@admin_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # นับจำนวนผู้ใช้แต่ละประเภท
    total_students = students_collection.count_documents({})
    total_teachers = teachers_collection.count_documents({})
    total_users = users_collection.count_documents({})
    
    # ดึงรายการคำขอที่ยังไม่ได้ยืนยัน (สำหรับอาจารย์)
    pending_teachers = users_collection.find({"role": "teacher", "is_verified": True, "is_approved": {"$ne": True}})
    
    return render_template('admin_dashboard.html',
                          first_name=first_name,
                          last_name=last_name,
                          total_students=total_students,
                          total_teachers=total_teachers,
                          total_users=total_users,
                          pending_teachers=list(pending_teachers))

@admin_bp.route('/role/student')
def switch_to_student():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # เปลี่ยน role ชั่วคราวเป็น student
    session['temp_role'] = 'student'
    flash('เปลี่ยนบทบาทเป็นนักศึกษาชั่วคราวเรียบร้อยแล้ว', 'success')
    return redirect(url_for('dashboard'))

@admin_bp.route('/role/teacher')
def switch_to_teacher():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # เปลี่ยน role ชั่วคราวเป็น teacher
    session['temp_role'] = 'teacher'
    flash('เปลี่ยนบทบาทเป็นอาจารย์ชั่วคราวเรียบร้อยแล้ว', 'success')
    return redirect(url_for('dashboard'))

@admin_bp.route('/role/admin')
def switch_to_admin():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # กลับไปใช้ role admin ตามปกติ
    if 'temp_role' in session:
        session.pop('temp_role')
    
    flash('กลับสู่บทบาทผู้ดูแลระบบเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/teachers')
def manage_teachers():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # ดึงรายการอาจารย์ทั้งหมด
    all_teachers = list(users_collection.find({"role": "teacher"}))
    
    # แยกประเภทอาจารย์
    pending_teachers = []
    active_teachers = []
    
    for teacher in all_teachers:
        # ถ้ามี is_approved เป็น True ถือว่าเป็นอาจารย์ที่ active แล้ว
        if teacher.get('is_approved', False):
            active_teachers.append(teacher)
        # ถ้าผ่านการยืนยันอีเมลแล้ว แต่ยังไม่ได้รับการอนุมัติ
        elif teacher.get('is_verified', False):
            pending_teachers.append(teacher)
    
    return render_template('admin_teachers.html',
                          first_name=first_name,
                          last_name=last_name,
                          pending_teachers=pending_teachers,
                          active_teachers=active_teachers)

@admin_bp.route('/teachers/approve/<teacher_id>', methods=['POST'])
def approve_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # อัพเดตสถานะการอนุมัติของอาจารย์
        teacher = users_collection.find_one({"_id": ObjectId(teacher_id)})
        
        if not teacher:
            flash('ไม่พบข้อมูลอาจารย์', 'danger')
            return redirect(url_for('admin.manage_teachers'))
        
        # ตรวจสอบว่าเป็นอาจารย์จริงหรือไม่
        if teacher.get('role') != 'teacher':
            flash('ผู้ใช้นี้ไม่ใช่อาจารย์', 'danger')
            return redirect(url_for('admin.manage_teachers'))
        
        # อัพเดตสถานะการอนุมัติ
        users_collection.update_one(
            {"_id": ObjectId(teacher_id)},
            {"$set": {
                "is_approved": True,
                "approved_at": datetime.now(ZoneInfo("Asia/Bangkok")),
                "approved_by": session.get('username')
            }}
        )
        
        # สร้างข้อมูลในคอลเลกชัน teachers
        teacher_data = {
            "username": teacher.get('username'),
            "first_name": teacher.get('first_name'),
            "last_name": teacher.get('last_name'),
            "email": teacher.get('email'),
            "role": "teacher",
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }
        
        # ตรวจสอบว่ามีข้อมูลอยู่แล้วหรือไม่
        existing_teacher = teachers_collection.find_one({"username": teacher.get('username')})
        
        if not existing_teacher:
            teachers_collection.insert_one(teacher_data)
        
        flash(f'อนุมัติอาจารย์ {teacher.get("first_name")} {teacher.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))

@admin_bp.route('/teachers/reject/<teacher_id>', methods=['POST'])
def reject_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ปฏิเสธการอนุมัติโดยการเปลี่ยน role เป็น student
        users_collection.update_one(
            {"_id": ObjectId(teacher_id)},
            {"$set": {
                "role": "student",
                "rejected_at": datetime.now(ZoneInfo("Asia/Bangkok")),
                "rejected_by": session.get('username')
            }}
        )
        
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        teacher = users_collection.find_one({"_id": ObjectId(teacher_id)})
        
        flash(f'ปฏิเสธคำขอของ {teacher.get("first_name")} {teacher.get("last_name")} และเปลี่ยนเป็นนักศึกษาเรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))

@admin_bp.route('/teachers/delete/<teacher_id>', methods=['POST'])
def delete_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        teacher = users_collection.find_one({"_id": ObjectId(teacher_id)})
        
        if not teacher:
            flash('ไม่พบข้อมูลอาจารย์', 'danger')
            return redirect(url_for('admin.manage_teachers'))
        
        # ลบข้อมูลจากทั้งสองคอลเลกชัน
        teachers_collection.delete_one({"username": teacher.get('username')})
        users_collection.delete_one({"_id": ObjectId(teacher_id)})
        
        flash(f'ลบอาจารย์ {teacher.get("first_name")} {teacher.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))

@admin_bp.route('/students')
def manage_students():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # ดึงรายการนักศึกษาทั้งหมด
    all_students = list(users_collection.find({"role": "student"}))
    
    return render_template('admin_students.html',
                          first_name=first_name,
                          last_name=last_name,
                          students=all_students)

@admin_bp.route('/students/delete/<student_id>', methods=['POST'])
def delete_student(student_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        student = users_collection.find_one({"_id": ObjectId(student_id)})
        
        if not student:
            flash('ไม่พบข้อมูลนักศึกษา', 'danger')
            return redirect(url_for('admin.manage_students'))
        
        # ลบข้อมูลจากทั้งสองคอลเลกชัน
        students_collection.delete_one({"username": student.get('username')})
        users_collection.delete_one({"_id": ObjectId(student_id)})
        
        flash(f'ลบนักศึกษา {student.get("first_name")} {student.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_students'))

@admin_bp.route('/users')
def manage_users():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
    last_name = user['last_name'] if user else session.get('last_name', 'User')
    
    # ดึงรายการผู้ใช้ทั้งหมด (ยกเว้นผู้ใช้ที่กำลังเข้าสู่ระบบ)
    all_users = list(users_collection.find({"_id": {"$ne": ObjectId(session['user_id'])}}))
    
    return render_template('admin_users.html',
                          first_name=first_name,
                          last_name=last_name,
                          users=all_users)

@admin_bp.route('/users/edit/<user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่ต้องการแก้ไข
    user_to_edit = users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user_to_edit:
        flash('ไม่พบข้อมูลผู้ใช้', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    current_user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = current_user['first_name'] if current_user else session.get('first_name', 'Unknown')
    last_name = current_user['last_name'] if current_user else session.get('last_name', 'User')
    
    if request.method == 'POST':
        # รับข้อมูลจากฟอร์ม
        username = request.form.get('username')
        first_name_edit = request.form.get('first_name')
        last_name_edit = request.form.get('last_name')
        email = request.form.get('email')
        role = request.form.get('role')
        is_verified = 'is_verified' in request.form
        is_approved = 'is_approved' in request.form
        
        # ตรวจสอบว่า username ซ้ำหรือไม่ (ถ้ามีการเปลี่ยน)
        if username != user_to_edit.get('username'):
            existing_user = users_collection.find_one({"username": username})
            if existing_user:
                flash('ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!', 'danger')
                return render_template('admin_edit_user.html',
                                      first_name=first_name,
                                      last_name=last_name,
                                      user=user_to_edit)
        
        # อัพเดตข้อมูลในคอลเลกชัน users_all
        update_data = {
            "username": username,
            "first_name": first_name_edit,
            "last_name": last_name_edit,
            "email": email,
            "role": role,
            "is_verified": is_verified,
            "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }
        
        if role == 'teacher':
            update_data["is_approved"] = is_approved
        
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        # อัพเดตข้อมูลในคอลเลกชัน students หรือ teachers
        if role == 'student':
            # ลบข้อมูลจาก teachers ถ้ามี
            teachers_collection.delete_one({"username": user_to_edit.get('username')})
            
            # อัพเดตหรือเพิ่มข้อมูลใน students
            student_data = {
                "username": username,
                "first_name": first_name_edit,
                "last_name": last_name_edit,
                "email": email,
                "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            }
            
            students_collection.update_one(
                {"username": user_to_edit.get('username')},
                {"$set": student_data},
                upsert=True
            )
        
        elif role == 'teacher' and is_approved:
            # ลบข้อมูลจาก students ถ้ามี
            students_collection.delete_one({"username": user_to_edit.get('username')})
            
            # อัพเดตหรือเพิ่มข้อมูลใน teachers
            teacher_data = {
                "username": username,
                "first_name": first_name_edit,
                "last_name": last_name_edit,
                "email": email,
                "updated_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            }
            
            teachers_collection.update_one(
                {"username": user_to_edit.get('username')},
                {"$set": teacher_data},
                upsert=True
            )
        
        flash('อัพเดตข้อมูลผู้ใช้เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template('admin_edit_user.html',
                          first_name=first_name,
                          last_name=last_name,
                          user=user_to_edit)

@admin_bp.route('/users/delete/<user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            flash('ไม่พบข้อมูลผู้ใช้', 'danger')
            return redirect(url_for('admin.manage_users'))
        
        # ลบข้อมูลจากคอลเลกชันที่เกี่ยวข้อง
        if user.get('role') == 'student':
            students_collection.delete_one({"username": user.get('username')})
        elif user.get('role') == 'teacher':
            teachers_collection.delete_one({"username": user.get('username')})
        
        # ลบข้อมูลจาก users_all
        users_collection.delete_one({"_id": ObjectId(user_id)})
        
        flash(f'ลบผู้ใช้ {user.get("first_name")} {user.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_users'))

# ฟังก์ชันเพิ่มผู้ใช้ใหม่
@admin_bp.route('/users/add', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
    current_user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
    first_name = current_user['first_name'] if current_user else session.get('first_name', 'Unknown')
    last_name = current_user['last_name'] if current_user else session.get('last_name', 'User')
    
    if request.method == 'POST':
        # รับข้อมูลจากฟอร์ม
        username = request.form.get('username')
        password = request.form.get('password')
        first_name_new = request.form.get('first_name')
        last_name_new = request.form.get('last_name')
        email = request.form.get('email')
        role = request.form.get('role')
        is_verified = 'is_verified' in request.form
        is_approved = 'is_approved' in request.form
        
        # ตรวจสอบว่า username ซ้ำหรือไม่
        existing_user = users_collection.find_one({"username": username})
        if existing_user:
            flash('ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!', 'danger')
            return render_template('admin_add_user.html',
                                  first_name=first_name,
                                  last_name=last_name)
        
        # ตรวจสอบว่า email ซ้ำหรือไม่
        existing_email = users_collection.find_one({"email": email})
        if existing_email:
            flash('อีเมลนี้ถูกใช้ไปแล้ว!', 'danger')
            return render_template('admin_add_user.html',
                                  first_name=first_name,
                                  last_name=last_name)
        
        # เข้ารหัสพาสเวิร์ด
        from flask_bcrypt import Bcrypt
        bcrypt = Bcrypt()
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # สร้างข้อมูลผู้ใช้ใหม่
        new_user = {
            "username": username,
            "password": hashed_password,
            "first_name": first_name_new,
            "last_name": last_name_new,
            "email": email,
            "role": role,
            "is_verified": is_verified,
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
        }
        
        if role == 'teacher':
            new_user["is_approved"] = is_approved
        
        # เพิ่มข้อมูลลงคอลเลกชัน users_all
        user_id = users_collection.insert_one(new_user).inserted_id
        
        # เพิ่มข้อมูลลงคอลเลกชัน students หรือ teachers
        if role == 'student':
            student_data = {
                "username": username,
                "first_name": first_name_new,
                "last_name": last_name_new,
                "email": email,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            }
            
            students_collection.insert_one(student_data)
        
        elif role == 'teacher' and is_approved:
            teacher_data = {
                "username": username,
                "first_name": first_name_new,
                "last_name": last_name_new,
                "email": email,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok"))
            }
            
            teachers_collection.insert_one(teacher_data)
        
        flash(f'เพิ่มผู้ใช้ {first_name_new} {last_name_new} เรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template('admin_add_user.html',
                          first_name=first_name,
                          last_name=last_name)

@admin_bp.route('/update_created_at')
def update_created_at():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    # ตรวจสอบว่าฟังก์ชันนี้อัพเดตข้อมูลในฐานข้อมูลจริงๆ
    result = users_collection.update_many(
        {"created_at": {"$exists": False}},
        {"$set": {"created_at": datetime.now(ZoneInfo("Asia/Bangkok"))}}
    )
    
    flash(f'อัพเดตฟิลด์ created_at สำหรับผู้ใช้ {result.modified_count} ราย', 'success')
    return redirect(url_for('admin.manage_users'))

