from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
import os
from werkzeug.utils import secure_filename
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz
    ZoneInfo = lambda tz: pytz.timezone(tz)

# สร้าง Blueprint สำหรับการจัดการไฟล์ PDF
pdf_bp = Blueprint('pdf_manager', __name__)

# ตั้งค่าที่เก็บไฟล์ PDF
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'pdfs')
ALLOWED_EXTENSIONS = {'pdf'}

# ตรวจสอบว่าไฟล์นามสกุลถูกต้องหรือไม่
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# API endpoint สำหรับอัปโหลดไฟล์ PDF
@pdf_bp.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'user_id' not in session or session.get('role') != 'teacher':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    if 'pdfFile' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part'}), 400
    
    file = request.files['pdfFile']
    lab_num = request.form.get('labNum')
    
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No selected file'}), 400
    
    if not lab_num or not lab_num.isdigit():
        return jsonify({'status': 'error', 'message': 'Invalid lab number'}), 400
    
    if file and allowed_file(file.filename):
        # สร้างชื่อไฟล์ตามรูปแบบ lab{lab_num}.pdf
        filename = f"lab{lab_num}.pdf"
        
        # ตรวจสอบว่าโฟลเดอร์มีอยู่หรือไม่ ถ้าไม่มีให้สร้าง
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # บันทึกไฟล์
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # บันทึกข้อมูลลงใน MongoDB
        try:
            from pymongo import MongoClient
            mongo_client = MongoClient('mongodb://localhost:27017/')
            db = mongo_client['network_users']
            pdf_collection = db.get_collection('lab_pdfs')
            
            pdf_collection.update_one(
                {"lab_num": int(lab_num)},
                {"$set": {
                    "filename": filename,
                    "path": file_path,
                    "updated_at": datetime.now(ZoneInfo("Asia/Bangkok")),
                    "updated_by": session.get('username', 'unknown')
                }},
                upsert=True
            )
        except Exception as e:
            print(f"Error updating database: {e}")
            # แม้จะมีข้อผิดพลาดในการอัปเดตฐานข้อมูล แต่ถ้าบันทึกไฟล์สำเร็จก็ให้ถือว่าสำเร็จ
        
        return jsonify({
            'status': 'success', 
            'message': 'File uploaded successfully',
            'filename': filename
        })
    
    return jsonify({'status': 'error', 'message': 'File type not allowed'}), 400