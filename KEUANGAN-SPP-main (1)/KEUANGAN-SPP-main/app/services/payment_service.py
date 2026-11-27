from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from app.models import db
from app.models.payment import Payment, PaymentReconciliation
from app.models.payment_method import PaymentMethod
from app.models.billing import Billing
from app.services.mail_service import queue_mail, deliver_outbox

class PaymentService:
    def __init__(self, app=None):
        self.app = app

    @staticmethod
    def sign_payload(payload, secret):
        data = {k: v for k, v in payload.items() if k != 'signature'}
        return hmac.new(secret.encode(), json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _verify_webhook_signature(payload, secret):
        signature = payload.get('signature')
        return isinstance(signature, str) and hmac.compare_digest(signature, PaymentService.sign_payload(payload, secret))

    def process_payment(self, billing_id, amount, payment_method_id, transaction_id, gateway_name='manual', payload=None):
        try:
            if type(billing_id) is not int or type(payment_method_id) is not int:
                raise ValueError('ID tagihan dan metode harus berupa angka bulat')
            value = Decimal(str(amount))
            if isinstance(amount, bool) or not value.is_finite() or value <= 0 or value != value.to_integral_value():
                raise ValueError('Nominal harus bilangan Rupiah positif tanpa pecahan')
            amount = int(value)
            if not isinstance(transaction_id, str) or not transaction_id.strip():
                raise ValueError('transaction_id wajib diisi')
            existing = Payment.query.filter_by(transaction_id=transaction_id).first()
            if existing:
                if existing.billing_id != billing_id or existing.amount != amount or existing.payment_method_id != payment_method_id:
                    raise ValueError('transaction_id sudah dipakai untuk pembayaran berbeda')
                return dict(success=True, message='Transaksi sudah diproses', payment=existing, billing=existing.billing, payment_id=existing.id, duplicate=True)
            billing = db.session.get(Billing, billing_id)
            method = db.session.get(PaymentMethod, payment_method_id)
            if not billing or not method or not method.is_active:
                raise ValueError('Tagihan/metode pembayaran tidak valid')
            previous = billing.paid_amount
            penalty = max(billing.penalty, billing.calculate_penalty(current_app.config['OVERDUE_PENALTY_PER_DAY'], current_app.config['OVERDUE_MAX_PENALTY']))
            total = billing.total_amount + penalty
            if amount > total - previous:
                raise ValueError('Pembayaran melebihi sisa tagihan termasuk denda')
            paid = previous + amount
            status = 'paid' if paid >= total else ('overdue' if billing.is_overdue else 'partial')
            now = datetime.utcnow()
            changed = db.session.execute(update(Billing).where(Billing.id == billing_id, Billing.paid_amount == previous).values(paid_amount=paid, penalty=penalty, remaining_amount=total-paid, status=status, last_payment_date=now))
            if changed.rowcount != 1:
                raise ValueError('Tagihan berubah saat diproses; ulangi pembayaran')
            payment = Payment(student_id=billing.student_id, billing_id=billing.id, payment_method_id=method.id, transaction_id=transaction_id, reference_code=Payment.generate_reference_code(), amount=amount, status='confirmed', gateway_name=gateway_name, gateway_response=payload, payment_date=now, confirmation_date=now)
            db.session.add(payment)
            db.session.flush()
            if payload is not None:
                db.session.add(PaymentReconciliation(payment_id=payment.id, gateway_name=gateway_name, status='synced', gateway_response=payload))
            queue_mail(f'receipt:{payment.id}', billing.student.email, 'Bukti Pembayaran SPP', f'NIM: {billing.student.nim}\nReferensi: {payment.reference_code}\nSemester: {billing.semester}\nPembayaran: Rp {amount:,}\nSisa: Rp {total-paid:,}\nStatus: {status}')
            db.session.commit()
        except (ValueError, InvalidOperation) as exc:
            db.session.rollback()
            return dict(success=False, message=str(exc), status_code=400)
        except IntegrityError:
            db.session.rollback()
            # A concurrent delivery may already have committed the same transaction.
            existing = Payment.query.filter_by(transaction_id=transaction_id).first()
            if existing and existing.billing_id == billing_id and existing.amount == amount and existing.payment_method_id == payment_method_id:
                return dict(success=True, message='Transaksi sudah diproses', payment=existing, billing=existing.billing, payment_id=existing.id, duplicate=True)
            return dict(success=False, message='Konflik transaksi; ulangi dengan data yang benar', status_code=409)
        except Exception:
            db.session.rollback()
            return dict(success=False, message='Pembayaran gagal diproses', status_code=500)
        deliver_outbox()
        return dict(success=True, message='Pembayaran berhasil dicatat', payment=payment, billing=billing, payment_id=payment.id, duplicate=False)

    def handle_webhook(self, payload, webhook_secret):
        if not isinstance(payload, dict) or not self._verify_webhook_signature(payload, webhook_secret):
            return dict(success=False, message='Signature tidak valid', status_code=401)
        if payload.get('status') not in ['success', 'failed', 'pending']:
            return dict(success=False, message='Status tidak valid', status_code=400)
        if payload['status'] != 'success':
            return dict(success=True, message='Notifikasi diterima; saldo tagihan tidak berubah', status_code=200)
        billing = db.session.get(Billing, payload.get('billing_id')) if type(payload.get('billing_id')) is int else None
        if not billing or ('student_id' in payload and payload['student_id'] != billing.student_id):
            return dict(success=False, message='Tagihan/mahasiswa tidak cocok', status_code=400)
        result = self.process_payment(billing.id, payload.get('amount'), payload.get('payment_method_id'), payload.get('transaction_id'), 'webhook', payload)
        result.setdefault('status_code', 200 if result['success'] else 400)
        return result

    def get_payment_history(self, student_id, limit=10):
        return Payment.query.filter_by(student_id=student_id).order_by(Payment.created_at.desc()).limit(limit).all()

    def get_payment_statistics(self, start_date=None, end_date=None):
        query = Payment.query.filter_by(status='confirmed')
        if start_date: query = query.filter(Payment.confirmation_date >= start_date)
        if end_date: query = query.filter(Payment.confirmation_date <= end_date)
        rows = query.all()
        total = sum(p.amount for p in rows)
        return dict(total_payments=len(rows), total_amount=total, average_amount=total/len(rows) if rows else 0, payments=rows)
