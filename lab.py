from flask import Flask, render_template, Blueprint  # เพิ่มการนำเข้า Blueprint

lab_bp = Blueprint('lab', __name__)

@lab_bp.route('/lab1')
def lab1():
    return render_template('lab1.html')  # ใช้งาน render_template
