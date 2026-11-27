"""Build a signed webhook and optionally send it using curl."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import uuid
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
p = argparse.ArgumentParser()
p.add_argument('--billing-id', type=int, required=True)
p.add_argument('--amount', type=int, required=True)
p.add_argument('--method-id', type=int, default=1)
p.add_argument('--transaction-id', default=None)
p.add_argument('--url', default='http://127.0.0.1:5000/api/webhook/payment')
p.add_argument('--output', default='webhook_payload.json')
p.add_argument('--curl', action='store_true', help='Send with curl after saving the signed payload')
args = p.parse_args()
payload = dict(billing_id=args.billing_id, amount=args.amount, payment_method_id=args.method_id, transaction_id=args.transaction_id or 'GATEWAY-'+uuid.uuid4().hex, status='success')
secret = os.getenv('PAYMENT_GATEWAY_SECRET', 'webhook-secret')
message = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
payload['signature'] = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
Path(args.output).write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(f'Signed payload saved to {args.output}')
if args.curl:
    subprocess.run(['curl', '--fail-with-body', '-X', 'POST', args.url, '-H', 'Content-Type: application/json', '--data-binary', '@'+args.output], check=True)
