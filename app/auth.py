import secrets, json, hashlib
import secrets, time, hashlib
from itsdangerous import URLSafeSerializer, BadSignature
from datetime import datetime, timedelta
from flask import current_app, request, session
from ipaddress import ip_address
from .models import TrustedDevice
from flask_mail import Message
from app import db, mail
import time

def get_client_ip():
    xff = request.headers.get('X-Forwarded-For')
    return (xff.split(',')[0].strip() if xff else request.remote_addr)

def device_fingerprint():
    ua = (request.user_agent.string or '').encode()
    return hashlib.sha256(ua).hexdigest()

def has_valid_trusted_device(user):
    s = URLSafeSerializer(current_app.config['SECRET_KEY'], salt='trusted-device')
    tok = request.cookies.get('tdev')
    if not tok: return False
    try:
        data = s.loads(tok)
    except BadSignature:
        return False
    td = TrustedDevice.query.filter_by(user_id=user.id, device_token=data.get('tok')).first()
    return td and td.expires_at > datetime.utcnow()

def set_trusted_cookie(resp, user):
    tok = secrets.token_hex(32)
    td = TrustedDevice(user_id=user.id, device_token=tok,
                       created_at=datetime.utcnow(),
                       expires_at=datetime.utcnow()+timedelta(days=current_app.config['TFA_TRUST_DAYS']))
    db.session.add(td); db.session.commit()
    s = URLSafeSerializer(current_app.config['SECRET_KEY'], salt='trusted-device')
    resp.set_cookie('tdev', s.dumps({'tok': tok}),
                    max_age=current_app.config['TFA_TRUST_DAYS']*24*3600,
                    httponly=True, secure=True, samesite='Lax')
    return resp

def send_email_otp(to_email, code):
    subject = "Votre code de vérification"
    body = f"Votre code est : {code}\nIl expire dans 10 minutes."
    msg = Message(subject=subject,
                  recipients=[to_email],
                  body=body,
                  sender=current_app.config['MAIL_DEFAULT_SENDER'])
    mail.send(msg)

def issue_email_otp(user_id, to_email):
    code = f"{secrets.randbelow(1_000_000):06d}"
    session['email_otp'] = {'uid': user_id, 'code': code, 'ts': time.time(), 'tries': 0}
    send_email_otp(to_email, code)
