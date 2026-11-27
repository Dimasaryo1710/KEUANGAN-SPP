import io
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from app import create_app, db
from app.models.billing import Billing, Semester
from app.models.payment import Payment, PaymentReconciliation
from app.models.notification import Notification, KRSRegistration
from app.models.student import Student
from app.services.payment_service import PaymentService
from app.services.billing_service import BillingService
from app.services.mail_service import deliver_outbox
from app.schedulers.billing_scheduler import generate_billing_job, update_penalty_job, send_reminder_job, setup_billing_scheduler

class FinanceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.assertEqual(self.client.post('/api/demo/init').status_code,201)
        self.bill = Billing.query.first()
        self.student_id = self.bill.student_id
        self.semester = Semester.query.filter_by(is_active=True).first()
        self.secret = self.app.config['PAYMENT_GATEWAY_SECRET']

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def pay(self, amount=None, transaction='txn-test'):
        return self.client.post('/api/webhook/simulate-payment',json=dict(billing_id=self.bill.id,student_id=self.student_id,amount=amount or self.bill.remaining_amount,payment_method_id=1,transaction_id=transaction))

    def signed(self, **changes):
        data=dict(billing_id=self.bill.id,student_id=self.student_id,amount=self.bill.remaining_amount,payment_method_id=1,transaction_id='signed-1',status='success')
        data.update(changes)
        data['signature']=PaymentService.sign_payload(data,self.secret)
        return data

    def test_due_date_and_duplicate_generation(self):
        self.assertEqual(self.bill.due_date,self.semester.start_date+timedelta(days=14))
        self.assertEqual(Billing.query.count(),4)
        generate_billing_job()
        self.assertEqual(Billing.query.count(),4)

    def test_scheduler_with_context(self):
        self.app.config['SCHEDULER_ENABLED']=True
        self.app.testing=False
        setup_billing_scheduler(self.app)
        scheduler=self.app.extensions['billing_scheduler']
        try:
            self.assertEqual(len(scheduler.get_jobs()),4)
            # Deliberately remove request/app context, as the scheduler does.
            self.ctx.pop()
            try: scheduler.get_job('billing').func()
            finally: self.ctx.push()
            self.assertEqual(Billing.query.count(),4)
        finally:
            scheduler.shutdown(wait=True)

    def test_future_semester_not_generated(self):
        semester=Semester(name='Future',start_date=datetime.utcnow()+timedelta(days=40),end_date=datetime.utcnow()+timedelta(days=100),is_active=True)
        db.session.add(semester);db.session.commit()
        generate_billing_job()
        self.assertEqual(Billing.query.filter_by(semester='Future').count(),0)

    def test_webhook_full_and_replay(self):
        data=self.signed()
        for _ in range(2):
            self.assertEqual(self.client.post('/api/webhook/payment',json=data).status_code,200)
        db.session.refresh(self.bill)
        self.assertEqual(self.bill.status,'paid')
        self.assertEqual(self.bill.remaining_amount,0)
        self.assertEqual(Payment.query.count(),1)
        self.assertEqual(PaymentReconciliation.query.count(),1)
        self.assertEqual(Notification.query.count(),1)

    def test_tamper_signature_and_unsigned(self):
        data=self.signed();data['amount']=1
        self.assertEqual(self.client.post('/api/webhook/payment',json=data).status_code,401)
        data.pop('signature')
        self.assertEqual(self.client.post('/api/webhook/payment',json=data).status_code,401)
        self.assertEqual(Payment.query.count(),0)

    def test_signed_pending_and_failed_do_not_pay(self):
        for status in ['pending','failed']:
            self.assertEqual(self.client.post('/api/webhook/payment',json=self.signed(status=status)).status_code,200)
        self.assertEqual(Payment.query.count(),0)
        self.assertEqual(self.bill.paid_amount,0)

    def test_student_mismatch(self):
        self.assertEqual(self.client.post('/api/webhook/payment',json=self.signed(student_id=999)).status_code,400)
        self.assertEqual(Payment.query.count(),0)

    def test_partial_then_full(self):
        self.assertEqual(self.pay(1000000).status_code,200)
        db.session.refresh(self.bill)
        self.assertEqual(self.bill.status,'partial')
        self.assertEqual(self.pay(transaction='txn-final').status_code,200)
        self.assertEqual(Payment.query.count(),2)
        self.assertEqual(self.bill.status,'paid')

    def test_overpayment_and_fraction_rejected(self):
        for amount in [self.bill.remaining_amount+1, 1.5, -1, True, 'abc']:
            result=self.pay(amount)
            self.assertEqual(result.status_code,400,result.json)
        self.assertEqual(Payment.query.count(),0)

    def test_transaction_conflict(self):
        self.pay(1000000)
        self.assertEqual(self.pay(2000000).status_code,400)
        self.assertEqual(Payment.query.count(),1)
        self.assertEqual(self.bill.paid_amount,1000000)

    def test_penalty_is_payable_and_krs_blocked(self):
        self.bill.due_date=datetime.utcnow()-timedelta(days=10)
        db.session.commit()
        update_penalty_job()
        self.assertEqual(self.bill.penalty,100000)
        self.assertEqual(self.bill.remaining_amount,self.bill.total_amount+100000)
        self.assertEqual(self.bill.status,'overdue')
        self.assertEqual(self.pay(self.bill.total_amount).status_code,200)
        self.assertFalse(BillingService().can_student_register_krs(self.student_id)['can_register'])
        self.pay(transaction='penalty-payment')
        self.assertEqual(self.bill.status,'paid')

    def test_actual_krs_registration(self):
        data=dict(student_id=self.student_id,semester_id=self.semester.id,courses=['IF101'])
        self.assertEqual(self.client.post('/api/krs/register',json=data).status_code,403)
        self.assertEqual(KRSRegistration.query.count(),0)
        self.pay()
        self.assertEqual(self.client.post('/api/krs/register',json=data).status_code,201)
        self.assertEqual(self.client.post('/api/krs/register',json=data).status_code,409)
        self.assertEqual(KRSRegistration.query.count(),1)

    def test_receipt_and_reminder_deduplication(self):
        self.bill.due_date=datetime.utcnow()+timedelta(days=1)
        db.session.commit()
        send_reminder_job();send_reminder_job()
        self.assertEqual(Notification.query.count(),1)
        self.pay()
        self.assertEqual(Notification.query.count(),2)
        self.assertTrue(all(n.status=='simulated' for n in Notification.query.all()))

    def test_smtp_failure_retry(self):
        self.app.config['MAIL_BACKEND']='smtp'
        with patch('app.services.mail_service.smtplib.SMTP',side_effect=OSError('SMTP unavailable')):
            result=self.pay()
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.bill.status,'paid')
        self.assertEqual(Notification.query.first().status,'failed')
        with patch('app.services.mail_service.smtplib.SMTP') as smtp:
            deliver_outbox()
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
        self.assertEqual(Notification.query.first().status,'sent')

    def test_atomic_rollback_if_receipt_queue_fails(self):
        with patch('app.services.payment_service.queue_mail',side_effect=RuntimeError('outbox unavailable')):
            self.assertEqual(self.pay().status_code,500)
        db.session.refresh(self.bill)
        self.assertEqual(self.bill.paid_amount,0)
        self.assertEqual(Payment.query.count(),0)
        self.assertEqual(PaymentReconciliation.query.count(),0)

    def test_report_aggregates_student_and_month(self):
        self.pay()
        second=Billing(student_id=self.student_id,semester='old-semester',total_amount=1000000,remaining_amount=1000000,due_date=datetime.utcnow()-timedelta(days=80))
        db.session.add(second);db.session.commit()
        report=self.client.get('/api/reports/finance').json
        self.assertEqual(report['revenue_metrics']['total_revenue'],5000000)
        self.assertEqual(report['outstanding']['students_over_two_months'],1)
        self.assertEqual(len({r['student_nim'] for r in report['top_outstanding_billings']}),len(report['top_outstanding_billings']))
        self.assertEqual(len(report['monthly_payments']),12)
        self.assertEqual(report['monthly_payments'][-1]['amount'],5000000)

    def test_csv_valid_and_invalid_no_database_writes(self):
        csv=f'nim,jumlah,tanggal,status\nTI2026001,123456,{datetime.utcnow():%Y-%m-%d},paid\nTI2026001,500,{datetime.utcnow():%Y-%m-%d},failed\n'
        response=self.client.post('/api/reports/finance/csv',data={'file':(io.BytesIO(csv.encode()),'test.csv')})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['revenue_metrics']['total_revenue'],123456)
        self.assertEqual(Payment.query.count(),0)
        response=self.client.post('/api/reports/finance/csv',data={'file':(io.BytesIO(b'wrong,columns\n1,2'),'bad.csv')})
        self.assertEqual(response.status_code,400)

    def test_endpoints_and_template(self):
        for path in ['/dashboard','/api/dashboard/summary','/api/dashboard/program-studi-stats','/api/dashboard/financial-report','/api/dashboard/students-status?status=unpaid','/api/payment/methods','/api/notifications']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,(path,response.json))
        self.assertEqual(len(self.client.get('/api/dashboard/students-status?status=unpaid').json['students']),4)

if __name__ == '__main__': unittest.main()
