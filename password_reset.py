import secrets
import logging
from flask import jsonify, request, session, current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash
from pymongo import MongoClient
from datetime import datetime
from zoneinfo import ZoneInfo

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('password_reset.log')
    ]
)

# เชื่อมต่อ MongoDB
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['network_users']
users_collection = db['users_all']

def send_reset_email(email, new_password):
    """
    ฟังก์ชันส่งอีเมลรหัสผ่านใหม่
    
    Args:
        email (str): อีเมลผู้รับ
        new_password (str): รหัสผ่านใหม่
    
    Returns:
        bool: สถานะการส่งอีเมล
    """
    try:
        # ใช้ mail จาก current_app.extensions แทนการ import จาก app.py
        mail = current_app.extensions['mail']
        
        msg = Message(
            'รหัสผ่านใหม่สำหรับระบบ Network Lab',
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=[email]
        )
        msg.body = f"""
        รหัสผ่านใหม่ของคุณคือ: {new_password}
        
        กรุณาเข้าสู่ระบบและเปลี่ยนรหัสผ่านทันที
        
        เวลาที่ส่งอีเมล: {datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        mail.send(msg)
        
        logging.info(f"ส่งอีเมลรหัสผ่านใหม่ไปยัง {email} สำเร็จ")
        return True
    except Exception as e:
        logging.error(f"เกิดข้อผิดพลาดในการส่งอีเมลถึง {email}: {str(e)}")
        return False

def reset_student_password_view():
    """
    ฟังก์ชันรีเซ็ตรหัสผ่านของนักศึกษา
    
    Returns:
        JSON response แสดงสถานะการรีเซ็ตรหัสผ่านและรหัสผ่านใหม่
    """
    # ตรวจสอบสิทธิ์
    if 'user_id' not in session or (session.get('role') != 'teacher' and session.get('temp_role') != 'teacher'):
        logging.warning("พยายามเข้าถึงการรีเซ็ตรหัสผ่านโดยไม่มีสิทธิ์")
        return jsonify({
            'success': False, 
            'message': 'คุณไม่มีสิทธิ์เข้าถึง'
        }), 403
    
    # รับข้อมูล
    data = request.get_json()
    student_ids = data.get('student_ids', [])
    
    if not student_ids:
        logging.warning("ไม่มีรหัสนักศึกษาที่ระบุ")
        return jsonify({
            'success': False, 
            'message': 'ไม่มีรหัสนักศึกษาที่ระบุ'
        }), 400
    
    successful_resets = []
    failed_resets = []
    password_info = {}  # เก็บข้อมูลรหัสผ่านใหม่
    
    for student_id in student_ids:
        try:
            # ค้นหาผู้ใช้
            user = users_collection.find_one({"username": student_id})
            
            if not user:
                logging.warning(f"ไม่พบผู้ใช้: {student_id}")
                failed_resets.append(student_id)
                continue
            
            # สร้างรหัสผ่านใหม่
            new_password = f"reset_{secrets.token_hex(3)}"
            
            # แฮชรหัสผ่าน
            hashed_password = generate_password_hash(new_password)
            
            # อัพเดทรหัสผ่าน
            update_result = users_collection.update_one(
                {"username": student_id}, 
                {"$set": {
                    "password": hashed_password,
                    "password_reset_time": datetime.now(ZoneInfo('Asia/Bangkok')).replace(microsecond=0)
                }}
            )
            
            if update_result.modified_count == 0:
                logging.error(f"ไม่สามารถอัพเดทรหัสผ่านสำหรับ {student_id}")
                failed_resets.append(student_id)
                continue
            
            # เก็บรหัสผ่านใหม่ไว้เพื่อส่งกลับ
            successful_resets.append(student_id)
            password_info[student_id] = {
                "password": new_password,
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}"
            }
            
            # พยายามส่งอีเมล (ถ้าต้องการ)
            try:
                send_reset_email(user.get('email', ''), new_password)
            except Exception as email_err:
                logging.warning(f"ไม่สามารถส่งอีเมลถึง {student_id}: {str(email_err)}")
                # ไม่นับว่าล้มเหลวเพราะรหัสผ่านถูกรีเซ็ตสำเร็จแล้ว
        
        except Exception as e:
            logging.error(f"เกิดข้อผิดพลาดในการรีเซ็ตรหัสผ่านสำหรับ {student_id}: {str(e)}")
            failed_resets.append(student_id)
    
    # บันทึกกิจกรรมการรีเซ็ตรหัสผ่าน
    if successful_resets:
        logging.info(f"รีเซ็ตรหัสผ่านสำเร็จสำหรับ: {successful_resets}")
    
    if failed_resets:
        logging.warning(f"การรีเซ็ตรหัสผ่านล้มเหลวสำหรับ: {failed_resets}")
    
    return jsonify({
        'success': True,
        'successful_resets': successful_resets,
        'failed_resets': failed_resets,
        'password_info': password_info  # ส่งข้อมูลรหัสผ่านกลับไป
    })

def init_routes(teacher_bp):
    """
    เพิ่มเส้นทางสำหรับการรีเซ็ตรหัสผ่าน
    
    Args:
        teacher_bp (Blueprint): Blueprint ของอาจารย์
    """
    @teacher_bp.route('/reset_student_password', methods=['POST'])
    def reset_student_password():
        return reset_student_password_view()