from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
from bson import ObjectId
import json
import logging
from flask_bcrypt import Bcrypt
import traceback

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

admin_bp = Blueprint('admin', __name__)

# เชื่อมต่อกับ MongoDB
from pymongo import MongoClient, errors

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('admin_activity.log', encoding='utf-8')
    ]
)

try:
    # เพิ่มการตั้งค่า timeout และ connection
    mongo_client = MongoClient(
        'mongodb://localhost:27017/', 
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000
    )
    
    # ตรวจสอบการเชื่อมต่อ
    mongo_client.server_info()
    bcrypt = Bcrypt()  # หรือใช้ Bcrypt(app) หากต้องการ
    db = mongo_client['network_users']
    users_collection = db['users_all']
    teachers_collection = db['teachers']
    students_collection = db['students']
    scores_collection = db['scores']
    logging.info("MongoDB connection established successfully")

except (errors.ConnectionFailure, errors.ServerSelectionTimeoutError) as e:
    logging.error(f"MongoDB connection error: {e}")
    
    # กำหนดค่าเริ่มต้นเมื่อเชื่อมต่อไม่สำเร็จ
    users_collection = None
    teachers_collection = None
    students_collection = None
    scores_collection = None
    
def check_mongodb_connection():
    """ตรวจสอบการเชื่อมต่อ MongoDB"""
    try:
        mongo_client.admin.command('ismaster')
        return True
    except Exception as e:
        logging.error(f"MongoDB connection check failed: {e}")
        return False

@admin_bp.route('/dashboard')
def dashboard():
    try:
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
            return redirect(url_for('login'))
        
        if not check_mongodb_connection():
            flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
            return redirect(url_for('login'))
        
        logging.info(f"Admin dashboard accessed: {session.get('username')}")
        
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        
        if not user:
            flash('ไม่พบข้อมูลผู้ใช้', 'danger')
            return redirect(url_for('login'))
        
        first_name = user['first_name']
        last_name = user['last_name']
        
        # คำนวณสถิติ
        total_students = students_collection.count_documents({})
        total_teachers = teachers_collection.count_documents({})
        total_users = users_collection.count_documents({})
        
        # ดึงรายการอาจารย์รอการอนุมัติ
        pending_teachers = list(users_collection.find({
            "role": "teacher", 
            "is_verified": True, 
            "is_approved": {"$ne": True}
        }))
        
        # *** แก้ไขตรงนี้: ไม่ต้องใช้ strftime กับวันที่ที่เป็น string อยู่แล้ว ***
        # ไม่ต้องแปลงรูปแบบวันที่ให้กับ pending_teachers

        # เพิ่มตัวแปรจำนวนอาจารย์ที่รออนุมัติ
        pending_teachers_count = len(pending_teachers)
        
        return render_template('admin_dashboard.html',
                              first_name=first_name,
                              last_name=last_name,
                              total_students=total_students,
                              total_teachers=total_teachers,
                              total_users=total_users,
                              pending_teachers=pending_teachers,
                              pending_teachers_count=pending_teachers_count)
    
    except Exception as e:
        logging.error(f"Error in admin dashboard: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
        return redirect(url_for('login'))

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
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
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
    
    except Exception as e:
        logging.error(f"Error in manage teachers: {e}")
        flash('เกิดข้อผิดพลาดในการจัดการอาจารย์', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/teachers/approve/<teacher_id>', methods=['POST'])
def approve_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
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
        
        current_time = datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
        # อัพเดตสถานะการอนุมัติ
        users_collection.update_one(
            {"_id": ObjectId(teacher_id)},
            {"$set": {
                "is_approved": True,
                "approved_at": current_time,
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
            "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
        }
        
        # ตรวจสอบว่ามีข้อมูลอยู่แล้วหรือไม่
        existing_teacher = teachers_collection.find_one({"username": teacher.get('username')})
        
        if not existing_teacher:
            teachers_collection.insert_one(teacher_data)
        
        logging.info(f"Teacher {teacher.get('username')} approved by {session.get('username')}")
        flash(f'อนุมัติอาจารย์ {teacher.get("first_name")} {teacher.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        logging.error(f"Error in approve teacher: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))

@admin_bp.route('/teachers/reject/<teacher_id>', methods=['POST'])
def reject_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ปฏิเสธการอนุมัติโดยการเปลี่ยน role เป็น student
        users_collection.update_one(
            {"_id": ObjectId(teacher_id)},
            {"$set": {
                "role": "student",
                "rejected_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0),
                "rejected_by": session.get('username')
            }}
        )
        
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        teacher = users_collection.find_one({"_id": ObjectId(teacher_id)})
        
        logging.info(f"Teacher {teacher.get('username')} rejected by {session.get('username')}")
        flash(f'ปฏิเสธคำขอของ {teacher.get("first_name")} {teacher.get("last_name")} และเปลี่ยนเป็นนักศึกษาเรียบร้อยแล้ว', 'success')
    except Exception as e:
        logging.error(f"Error in reject teacher: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))
@admin_bp.route('/teachers/delete/<teacher_id>', methods=['POST'])
def delete_teacher(teacher_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
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
        
        logging.info(f"Teacher {teacher.get('username')} deleted by {session.get('username')}")
        flash(f'ลบอาจารย์ {teacher.get("first_name")} {teacher.get("last_name")} เรียบร้อยแล้ว', 'success')
    except Exception as e:
        logging.error(f"Error in delete teacher: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_teachers'))

@admin_bp.route('/students')
def manage_students():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        first_name = user['first_name'] if user else session.get('first_name', 'Unknown')
        last_name = user['last_name'] if user else session.get('last_name', 'User')
        
        # ดึงรายการนักศึกษาทั้งหมด
        all_students = list(users_collection.find({"role": "student"}))
        # แปลง string เป็น datetime ถ้าจำเป็น
        for student in all_students:
            if 'created_at' in student and isinstance(student['created_at'], str):
                try:
                    # แปลง string เป็น datetime (ปรับ format ตามรูปแบบข้อมูลของคุณ)
                    student['created_at'] = datetime.strptime(student['created_at'], '%Y-%m-%d %H:%M:%S')
                except:
                    # ถ้าแปลงไม่ได้ ให้คงค่าเดิมไว้
                    pass
        return render_template('admin_students.html',
                              first_name=first_name,
                              last_name=last_name,
                              students=all_students)
    
    except Exception as e:
        logging.error(f"Error in manage students: {e}")
        flash('เกิดข้อผิดพลาดในการจัดการนักศึกษา', 'danger')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/students/delete/<student_id>', methods=['POST'])
def delete_student(student_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        student = users_collection.find_one({"_id": ObjectId(student_id)})
        
        if not student:
            flash('ไม่พบข้อมูลนักศึกษา', 'danger')
            return redirect(url_for('admin.manage_students'))
        
        # ลบข้อมูลคะแนนของนักศึกษา
        scores_collection = db['scores']  # เพิ่มบรรทัดนี้เพื่อเชื่อมต่อคอลเลกชันคะแนน
        scores_collection.delete_many({"student_id": student_id})
        scores_collection.delete_many({"username": student.get('username')})
        
        # ลบข้อมูลจากทั้งสองคอลเลกชัน
        students_collection.delete_one({"username": student.get('username')})
        users_collection.delete_one({"_id": ObjectId(student_id)})
        
        logging.info(f"Student {student.get('username')} and all related scores deleted by {session.get('username')}")
        flash(f'ลบนักศึกษา {student.get("first_name")} {student.get("last_name")} และข้อมูลคะแนนทั้งหมดเรียบร้อยแล้ว', 'success')
    except Exception as e:
        logging.error(f"Error in delete student: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_students'))
@admin_bp.route('/users')
def manage_users():
    logging.info("Entering manage_users function")
    
    if 'user_id' not in session or session.get('role') != 'admin':
        logging.info("User not authenticated or not admin, redirecting")
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        logging.info("MongoDB connection failed, redirecting")
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        logging.info("Starting manage_users main logic")
        
        # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
        current_user_id = session.get('user_id')
        logging.info(f"Current user ID: {current_user_id}")
        
        user = users_collection.find_one({"_id": ObjectId(current_user_id)})
        logging.info(f"Current user found: {user is not None}")
        
        first_name = user.get('first_name', '') if user else session.get('first_name', 'Unknown') 
        last_name = user.get('last_name', '') if user else session.get('last_name', 'User')
        
        # ดึงรายการผู้ใช้ทั้งหมด (ยกเว้นผู้ใช้ที่กำลังเข้าสู่ระบบ)
        logging.info("Fetching all users")
        all_users = list(users_collection.find({"_id": {"$ne": ObjectId(current_user_id)}}))
        logging.info(f"Found {len(all_users)} users")
        
        # แปลง ObjectId เป็น string
        for user_obj in all_users:
            if '_id' in user_obj:
                user_obj['_id'] = str(user_obj['_id'])
        
        logging.info("Rendering template")
        return render_template('admin_users.html',
                              first_name=first_name,
                              last_name=last_name,
                              users=all_users)
    
    except Exception as e:
        stack_trace = traceback.format_exc()
        logging.error(f"Error in manage users: {e}")
        logging.error(f"Stack trace: {stack_trace}")
        flash('เกิดข้อผิดพลาดในการจัดการผู้ใช้', 'danger')
        return redirect(url_for('admin.dashboard'))
    
@admin_bp.route('/users/edit/<user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
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
                "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
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
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
                }
                
                teachers_collection.update_one(
                    {"username": user_to_edit.get('username')},
                    {"$set": teacher_data},
                    upsert=True
                )
            
            logging.info(f"User {user_to_edit.get('username')} edited by {session.get('username')}")
            flash('อัพเดตข้อมูลผู้ใช้เรียบร้อยแล้ว', 'success')
            return redirect(url_for('admin.manage_users'))
        
        return render_template('admin_edit_user.html',
                              first_name=first_name,
                              last_name=last_name,
                              user=user_to_edit)
    
    except Exception as e:
        logging.error(f"Error in edit user: {e}")
        flash('เกิดข้อผิดพลาดในการแก้ไขข้อมูลผู้ใช้', 'danger')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/delete/<user_id>', methods=['POST'])
def delete_user(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้เพื่อแสดงข้อความ
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            flash('ไม่พบข้อมูลผู้ใช้', 'danger')
            return redirect(url_for('admin.manage_users'))
        
        # ลบข้อมูลจากคอลเลกชันที่เกี่ยวข้อง
        if user.get('role') == 'student':
            # ลบข้อมูลคะแนนของนักศึกษา
            scores_collection = db['scores']  # เพิ่มบรรทัดนี้เพื่อเชื่อมต่อคอลเลกชันคะแนน
            scores_collection.delete_many({"student_id": user_id})
            scores_collection.delete_many({"username": user.get('username')})
            students_collection.delete_one({"username": user.get('username')})
        elif user.get('role') == 'teacher':
            teachers_collection.delete_one({"username": user.get('username')})
        
        # ลบข้อมูลจาก users_all
        users_collection.delete_one({"_id": ObjectId(user_id)})
        
        logging.info(f"User {user.get('username')} and all related data deleted by {session.get('username')}")
        flash(f'ลบผู้ใช้ {user.get("first_name")} {user.get("last_name")} และข้อมูลที่เกี่ยวข้องทั้งหมดเรียบร้อยแล้ว', 'success')
    except Exception as e:
        logging.error(f"Error in delete user: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/add', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # ดึงข้อมูลผู้ใช้ที่เข้าสู่ระบบ
        current_user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        first_name = current_user['first_name'] if current_user else session.get('first_name', 'Unknown')
        last_name = current_user['last_name'] if current_user else session.get('last_name', 'User')
        
        if request.method == 'POST':
            # รับข้อมูลจากฟอร์ม
            username = request.form.get('username')
            first_name_new = request.form.get('first_name')
            last_name_new = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role')
            is_verified = 'is_verified' in request.form
            is_approved = 'is_approved' in request.form if role == 'teacher' else False
            
            # ตรวจสอบชื่อผู้ใช้ซ้ำ
            existing_user = users_collection.find_one({"username": username})
            if existing_user:
                flash('ชื่อผู้ใช้งานนี้ถูกใช้ไปแล้ว!', 'danger')
                return render_template('admin_add_user.html', 
                                       first_name=first_name, 
                                       last_name=last_name)
            
            # ตรวจสอบอีเมลซ้ำ
            existing_email = users_collection.find_one({"email": email})
            if existing_email:
                flash('อีเมลนี้ถูกใช้ไปแล้ว!', 'danger')
                return render_template('admin_add_user.html', 
                                       first_name=first_name, 
                                       last_name=last_name)
            
            # เข้ารหัสรหัสผ่าน
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            
            # เตรียมข้อมูลผู้ใช้
            user_data = {
                "username": username,
                "first_name": first_name_new,
                "last_name": last_name_new,
                "email": email,
                "password": hashed_password,
                "role": role,
                "is_verified": is_verified,
                "is_approved": is_approved if role == 'teacher' else False,
                "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
            }
            
            # เพิ่มผู้ใช้ลงในคอลเลกชัน users_all
            users_collection.insert_one(user_data)
            
            # เพิ่มข้อมูลในคอลเลกชันที่เกี่ยวข้อง
            if role == 'student':
                students_collection.insert_one({
                    "username": username,
                    "first_name": first_name_new,
                    "last_name": last_name_new,
                    "email": email,
                    "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
                })
            elif role == 'teacher' and is_approved:
                teachers_collection.insert_one({
                    "username": username,
                    "first_name": first_name_new,
                    "last_name": last_name_new,
                    "email": email,
                    "created_at": datetime.now(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
                })
            
            logging.info(f"New user added: {username} by {session.get('username')}")
            flash('เพิ่มผู้ใช้ใหม่สำเร็จ', 'success')
            return redirect(url_for('admin.manage_users'))
        
        # สำหรับ GET request
        return render_template('admin_add_user.html', 
                              first_name=first_name, 
                              last_name=last_name)
    
    except Exception as e:
        logging.error(f"Error in add user: {e}")
        flash('เกิดข้อผิดพลาดในการเพิ่มผู้ใช้', 'danger')
        return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/action=delete', methods=['POST'])
def bulk_action_delete():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('login'))
    
    if not check_mongodb_connection():
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลได้', 'danger')
        return redirect(url_for('login'))
    
    try:
        # รับข้อมูลจาก form หรือจาก request.args
        selected_ids = request.form.getlist('selected_ids')
        
        if not selected_ids:
            flash('กรุณาเลือกผู้ใช้ที่ต้องการลบ', 'warning')
            return redirect(url_for('admin.manage_users'))
        
        # ลบผู้ใช้ที่เลือก
        deleted_count = 0
        for user_id in selected_ids:
            try:
                # ดึงข้อมูลผู้ใช้ก่อนลบ
                user = users_collection.find_one({"_id": ObjectId(user_id)})
                
                if user:
                    username = user.get('username')
                    role = user.get('role')
                    
                    # ลบข้อมูลที่เกี่ยวข้อง
                    if role == 'student':
                        students_collection.delete_one({"username": username})
                        scores_collection.delete_many({"student_id": user_id})
                    elif role == 'teacher':
                        teachers_collection.delete_one({"username": username})
                    
                    # ลบผู้ใช้
                    users_collection.delete_one({"_id": ObjectId(user_id)})
                    deleted_count += 1
            except Exception as e:
                logging.error(f"Error deleting user {user_id}: {e}")
        
        flash(f'ลบผู้ใช้จำนวน {deleted_count} รายการเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin.manage_users'))
    
    except Exception as e:
        logging.error(f"Error in bulk action delete: {e}")
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
        return redirect(url_for('admin.manage_users'))
    
# เพิ่มฟังก์ชันที่ขาดหายไป หรือลบการอ้างอิงที่ไม่มีอยู่จริง
@admin_bp.route('/update_created_at', methods=['GET'])
def update_created_at():
    # ฟังก์ชันนี้เป็นเพียงตัวอย่าง คุณอาจต้องปรับให้เหมาะสม
    flash('ฟังก์ชันนี้ยังไม่ได้ถูกใช้งาน', 'warning')
    return redirect(url_for('admin.manage_users'))

