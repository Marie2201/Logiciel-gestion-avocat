from flask_mail import Message
from flask import url_for, render_template
from app import mail
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
import os
from email.utils import formataddr
from urllib.parse import urlparse, urljoin

def envoyer_mail_attribution(user, dossier):
    if not user or not user.email:
        return

    # URL complète vers le dossier
    lien_dossier = url_for('dossiers', _external=True) + f"#dossier-{dossier.id}"

    msg = Message(
        subject="📌 Nouveau dossier attribué",
        recipients=[user.email],
        body=f"""Bonjour {user.nom},

Un nouveau dossier vous a été attribué :

- 📁 Nom du dossier : {dossier.nom}
- 🏢 Client : {dossier.client.societe}
- 📅 Date d'ouverture : {dossier.date_ouverture.strftime('%d/%m/%Y')}
- 🔗 Lien direct : {lien_dossier}

Merci de vous connecter à la plateforme pour consulter ce dossier.

Bien cordialement,
Le Cabinet
"""
    )

    mail.send(msg)

def generate_reset_token(email: str) -> str:
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(email, salt=current_app.config.get('PASSWORD_RESET_SALT', 'pwd-reset-salt'))

def verify_reset_token(token: str, max_age_seconds: int = 3600) -> str | None:
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        return s.loads(token, salt=current_app.config.get('PASSWORD_RESET_SALT', 'pwd-reset-salt'),
                       max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def _clean_base(url: str) -> str:
    if not url:
        return ""
    url = url.strip().strip('"').strip("'").replace("<", "").replace(">", "")
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    return url

def reset_url_for(token: str) -> str:
    base = _clean_base(os.getenv("RESET_BASE_URL", ""))
    if base:
        p = urlparse(base)
        if p.scheme in ("http", "https") and p.netloc:
            return urljoin(f"{p.scheme}://{p.netloc}", f"/password/reset/{token}")
        current_app.logger.warning("⚠️ RESET_BASE_URL invalide: %r, fallback url_for", base)
    return url_for("reset_password", token=token, _external=True)

def _ts():
    secret = current_app.config["SECRET_KEY"]
    salt = current_app.config.get("RESET_SALT", "password-reset-v1")
    return URLSafeTimedSerializer(secret, salt=salt)

def make_reset_token(user):
    """Retourne un token signé qui encode id + email."""
    return _ts().dumps({"uid": user.id, "e": user.email})

def verify_reset_token(token, max_age=3600):
    """Retourne le dict payload si OK, 'expired' si expiré, None si invalide."""
    try:
        data = _ts().loads(token, max_age=max_age)
        return data
    except SignatureExpired:
        return "expired"
    except BadSignature:
        return None

def send_reset_email(user, token):
    reset_url = reset_url_for(token)  # <-- utilise ta fonction
    subject = "Réinitialisation de votre mot de passe"
    msg = Message(subject=subject, recipients=[user.email])
    msg.body = render_template('email/reset_password.txt', user=user, reset_url=reset_url)
    msg.html = render_template('email/reset_password.html', user=user, reset_url=reset_url)
    # (optionnel) msg.reply_to = current_app.config.get("MAIL_REPLY_TO")
    mail.send(msg)

# def reset_url_for(token):
#     base = os.getenv("RESET_BASE_URL")
#     if base:
#         return f"{base.rstrip('/')}/password/reset/{token}"  # ex: https://app.myhouda.com/password/reset/...
#     return url_for('reset_password', token=token, _external=True)