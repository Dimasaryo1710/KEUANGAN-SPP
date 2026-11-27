from flask import Blueprint, request, jsonify, current_app
from uuid import uuid4
from app.services.payment_service import PaymentService
from app.models.payment_method import PaymentMethod

webhook_bp = Blueprint('webhook', __name__, url_prefix='/api/webhook')
service = PaymentService()

def response(result):
    return jsonify(success=result['success'], message=result['message'], payment_id=result.get('payment_id'), duplicate=result.get('duplicate', False)), result.get('status_code', 200 if result['success'] else 400)

@webhook_bp.post('/payment')
def payment_webhook():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, message='JSON object wajib diisi'), 400
    return response(service.handle_webhook(data, current_app.config['PAYMENT_GATEWAY_SECRET']))

@webhook_bp.post('/simulate-payment')
def simulate_payment():
    if not current_app.debug and not current_app.testing:
        return jsonify(error='Hanya tersedia dalam development'), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='JSON object wajib diisi'), 400
    method = PaymentMethod.query.filter_by(is_active=True).first()
    payload = dict(data)
    payload.setdefault('transaction_id', 'SIM-'+uuid4().hex)
    payload.setdefault('status', 'success')
    payload.setdefault('payment_method_id', method.id if method else None)
    payload['signature'] = service.sign_payload(payload, current_app.config['PAYMENT_GATEWAY_SECRET'])
    return response(service.handle_webhook(payload, current_app.config['PAYMENT_GATEWAY_SECRET']))

@webhook_bp.get('/health')
def health():
    return jsonify(status='healthy')
