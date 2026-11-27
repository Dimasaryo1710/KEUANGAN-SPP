from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import smtplib
from flask import current_app
from app.models import db
from app.models.notification import Notification


def queue_mail(key, recipient, subject, body):
    existing = Notification.query.filter_by(dedupe_key=key).first()
    if existing:
        return existing
    item = Notification(dedupe_key=key, recipient=recipient, subject=subject, body=body)
    db.session.add(item)
    return item


def deliver_outbox():
    for item in Notification.query.filter(Notification.status.in_(['queued', 'failed'])).all():
        message = EmailMessage()
        message['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        message['To'] = item.recipient
        message['Subject'] = item.subject
        message.set_content(item.body)
        try:
            if current_app.config['MAIL_BACKEND'] == 'smtp':
                with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'], timeout=10) as smtp:
                    if current_app.config['MAIL_USE_TLS']:
                        smtp.starttls()
                    if current_app.config.get('MAIL_USERNAME'):
                        smtp.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
                    smtp.send_message(message)
                item.status = 'sent'
            else:
                directory = Path(current_app.instance_path) / 'outbox'
                directory.mkdir(parents=True, exist_ok=True)
                (directory / f'{item.id}.eml').write_bytes(message.as_bytes())
                item.status = 'simulated'
            item.sent_at = datetime.utcnow()
            item.error = None
        except Exception as exc:
            item.status = 'failed'
            item.error = str(exc)
        db.session.commit()
