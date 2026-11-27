from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, current_app
from sqlalchemy.exc import IntegrityError
from app.models import db
from app.models.billing import Billing, Semester
from app.models.student import Student, ProgramStudi
from app.models.payment_method import PaymentMethod
from app.models.notification import Notification, KRSRegistration
from app.services.billing_service import BillingService
from app.services.ai_service import AIFinancialService
from app.schedulers.billing_scheduler import generate_billing_job, update_penalty_job, send_reminder_job

extension_bp = Blueprint('extension', __name__)

@extension_bp.get('/dashboard')
def dashboard(): return render_template('finance.html')

@extension_bp.get('/api/payment/methods')
def methods():
    return jsonify(methods=[dict(id=m.id,name=m.name) for m in PaymentMethod.query.filter_by(is_active=True).all()])

@extension_bp.post('/api/semesters')
def add_semester():
    data = request.get_json(silent=True) or {}
    try:
        start = datetime.fromisoformat(data['start_date'])
        end = datetime.fromisoformat(data['end_date'])
        if start >= end or start.tzinfo or end.tzinfo: raise ValueError('Tanggal semester tidak valid')
        if data.get('is_active', True):
            for item in Semester.query.all(): item.is_active = False
        semester = Semester(name=data['name'], start_date=start, end_date=end, is_active=data.get('is_active',True))
        db.session.add(semester)
        db.session.commit()
        generate_billing_job()
        return jsonify(id=semester.id,name=semester.name),201
    except (KeyError, ValueError, TypeError, IntegrityError) as exc:
        db.session.rollback()
        return jsonify(error='Data semester tidak valid atau nama sudah digunakan'),400

@extension_bp.post('/api/krs/register')
def register_krs():
    data = request.get_json(silent=True) or {}
    try:
        sid, semester_id = data['student_id'], data['semester_id']
        if type(sid) is not int or type(semester_id) is not int: raise ValueError()
        semester = db.session.get(Semester,semester_id)
        if not semester or not semester.is_active: raise ValueError()
        update_penalty_job()
        eligibility = BillingService().can_student_register_krs(sid)
        if not eligibility['can_register']: return jsonify(eligibility),403
        if not Billing.query.filter_by(student_id=sid,semester=semester.name).first():
            return jsonify(error='Tagihan semester belum dibuat'),409
        courses = data.get('courses')
        if not isinstance(courses,list) or not courses or any(not isinstance(c,str) or not c.strip() for c in courses): raise ValueError()
        entry = KRSRegistration(student_id=sid,semester_id=semester_id,courses=courses)
        db.session.add(entry)
        db.session.commit()
        return jsonify(success=True,id=entry.id,message='KRS berhasil disimpan'),201
    except (KeyError, ValueError, TypeError):
        return jsonify(error='Isi student_id, semester_id aktif, dan courses berupa daftar kode MK'),400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='KRS semester ini sudah terdaftar'),409

@extension_bp.get('/api/reports/finance')
def finance_report():
    return jsonify(AIFinancialService().generate_financial_report())

@extension_bp.post('/api/reports/finance/csv')
def csv_report():
    try:
        file = request.files.get('file')
        if not file: return jsonify(error='Upload CSV melalui field file'),400
        if request.content_length and request.content_length > 2_000_000: return jsonify(error='CSV maksimum 2 MB'),413
        return jsonify(AIFinancialService().generate_financial_report(csv_text=file.read().decode('utf-8-sig')))
    except (ValueError,UnicodeError) as exc:
        return jsonify(error=str(exc)),400

@extension_bp.get('/api/notifications')
def notifications():
    return jsonify(backend=current_app.config['MAIL_BACKEND'], notifications=[dict(id=n.id,recipient=n.recipient,subject=n.subject,body=n.body,status=n.status,error=n.error) for n in Notification.query.order_by(Notification.id.desc()).limit(100)])

@extension_bp.post('/api/jobs/run')
def jobs():
    if not current_app.debug and not current_app.testing: return jsonify(error='Hanya development'),403
    generate_billing_job()
    update_penalty_job()
    send_reminder_job()
    return jsonify(success=True,message='Generate billing, denda, dan reminder selesai')

@extension_bp.post('/api/demo/init')
def demo():
    if not current_app.debug and not current_app.testing: return jsonify(error='Hanya development'),403
    if Student.query.count(): return jsonify(error='Data mahasiswa sudah ada; data tidak ditimpa'),409
    for name,code,amount in [('Teknik Informatika','TI',5000000),('Ekonomi','EK',4000000)]:
        prodi = ProgramStudi.query.filter_by(code=code).first()
        if not prodi:
            prodi=ProgramStudi(name=name,code=code,spp_amount=amount)
            db.session.add(prodi)
            db.session.flush()
        for i in range(1,3):
            db.session.add(Student(nim=f'{code}2026{i:03}',name=f'Mahasiswa {code} {i}',email=f'{code.lower()}{i}@example.test',program_studi_id=prodi.id,status='active'))
    if not PaymentMethod.query.count(): db.session.add(PaymentMethod(name='Transfer Simulasi',method_type='bank_transfer',is_active=True))
    if not Semester.query.filter_by(is_active=True).first():
        now=datetime.utcnow()
        db.session.add(Semester(name=f'Demo-{now:%Y%m%d%H%M%S}',start_date=now.replace(hour=0,minute=0,second=0,microsecond=0),end_date=now+timedelta(days=180),is_active=True))
    db.session.commit()
    generate_billing_job()
    return jsonify(success=True,message='4 mahasiswa demo dan tagihan berhasil dibuat'),201

@extension_bp.get('/api/programs')
def programs():
    return jsonify(programs=[dict(id=p.id,name=p.name,spp_amount=p.spp_amount) for p in ProgramStudi.query.all()])
