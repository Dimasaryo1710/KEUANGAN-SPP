from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import db
from app.models.billing import Billing, Semester
from app.services.billing_service import BillingService
from app.services.mail_service import queue_mail, deliver_outbox
from flask import current_app

scheduler = None

def generate_billing_job():
    now = datetime.utcnow()
    for semester in Semester.query.filter(Semester.is_active.is_(True), Semester.start_date <= now, Semester.end_date >= now).all():
        result = BillingService().generate_billing_for_semester(semester.id)
        if result['success']:
            semester.billing_generation_date = now
            db.session.commit()

def update_penalty_job():
    for bill in Billing.query.filter(Billing.status != 'paid').all():
        bill.penalty = max(bill.penalty, bill.calculate_penalty(current_app.config['OVERDUE_PENALTY_PER_DAY'], current_app.config['OVERDUE_MAX_PENALTY']))
        bill.remaining_amount = max(0, bill.total_amount + bill.penalty - bill.paid_amount)
        bill.update_status()
    db.session.commit()

def send_reminder_job():
    now = datetime.utcnow()
    for bill in Billing.query.filter(Billing.remaining_amount > 0, Billing.due_date <= now + timedelta(days=7)).all():
        queue_mail(f'reminder:{bill.id}:{now.date()}', bill.student.email, 'Reminder Pembayaran SPP', f'NIM: {bill.student.nim}\nSemester: {bill.semester}\nSisa: Rp {bill.remaining_amount:,}\nJatuh tempo: {bill.due_date:%d-%m-%Y}')
    db.session.commit()
    deliver_outbox()

def setup_billing_scheduler(app):
    global scheduler
    if app.testing or not app.config['SCHEDULER_ENABLED']:
        return
    scheduler = BackgroundScheduler(timezone='Asia/Jakarta')
    def wrapped(job):
        def run():
            with app.app_context():
                try:
                    job()
                except Exception:
                    db.session.rollback()
                    app.logger.exception('Scheduled job failed')
        return run
    scheduler.add_job(wrapped(generate_billing_job), 'interval', hours=1, next_run_time=datetime.utcnow(), id='billing', max_instances=1)
    scheduler.add_job(wrapped(update_penalty_job), 'cron', hour=0, minute=5, id='penalty')
    scheduler.add_job(wrapped(send_reminder_job), 'cron', hour=9, minute=0, id='reminder')
    scheduler.add_job(wrapped(deliver_outbox), 'interval', minutes=5, id='outbox')
    scheduler.start()
    app.extensions['billing_scheduler'] = scheduler

def shutdown_scheduler():
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
