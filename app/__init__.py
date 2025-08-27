from flask import Flask, make_response
from flask_sqlalchemy import SQLAlchemy
import os
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_talisman import Talisman
from werkzeug.exceptions import RequestEntityTooLarge
from flask import redirect, request, flash, url_for

# ----- ENV -----
load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)

if os.getenv("FLASK_ENV") == "development":
    talisman = Talisman(app, content_security_policy=None, force_https=False)
else:
    talisman = Talisman(app, content_security_policy=None, force_https=True)
#talisman = Talisman(app, content_security_policy=None)

# ----- CONFIG APP -----
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True
app.config['SQLALCHEMY_ECHO'] = True
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = False
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# ✅ NE PAS fixer SERVER_NAME en local (garde-le pour la prod via .env)
# app.config["SERVER_NAME"] = os.getenv("SERVER_NAME")  # ex: "app.myhouda.com"
# app.config["PREFERRED_URL_SCHEME"] = os.getenv("PREFERRED_URL_SCHEME", "https")
@app.errorhandler(RequestEntityTooLarge)
def handle_413(e):
    flash("Fichier trop volumineux. Limite : 100 Mo.", "danger")
    return redirect(request.referrer or url_for('documents'))
# ----- Helpers ENV -----
def getenv_clean(key, default=""):
    return os.getenv(key, default).strip().strip('"').strip("'")

def getenv_bool(key, default=False):
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

# ----- SMTP OVH -----
app.config["MAIL_SERVER"]        = getenv_clean("MAIL_SERVER") or "ssl0.ovh.net"
app.config["MAIL_PORT"]          = int(os.getenv("MAIL_PORT", "465"))
app.config["MAIL_USE_SSL"]       = getenv_bool("MAIL_USE_SSL", True)   # OVH 465
app.config["MAIL_USE_TLS"]       = getenv_bool("MAIL_USE_TLS", False)  # OVH 587 => True, SSL False
app.config["MAIL_USERNAME"]      = getenv_clean("MAIL_USERNAME")       # no-reply@myhouda.com
app.config["MAIL_PASSWORD"]      = getenv_clean("MAIL_PASSWORD")
# Tu peux laisser tuple (Nom, Email) ou simplement l'email:
# app.config["MAIL_DEFAULT_SENDER"] = (os.getenv("MAIL_FROM_NAME","Cabinet"),
#                                      app.config["MAIL_USERNAME"] or "no-reply@myhouda.com")
app.config["MAIL_DEFAULT_SENDER"]= app.config["MAIL_USERNAME"] or "no-reply@myhouda.com"
app.config["MAIL_SUPPRESS_SEND"] = False
app.config["MAIL_TIMEOUT"]       = 30
app.config.setdefault("RESET_SALT", "password-reset-v1")

mail = Mail()
mail.init_app(app)   # ✅ une seule initialisation

# Log clair au démarrage
app.logger.info(
    "SMTP → host=%r port=%s SSL=%s TLS=%s sender=%r",
    app.config["MAIL_SERVER"],
    app.config["MAIL_PORT"],
    app.config["MAIL_USE_SSL"],
    app.config["MAIL_USE_TLS"],
    app.config["MAIL_DEFAULT_SENDER"],
)

# ----- Extensions -----
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
moment = Moment(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----- Noindex global -----
@app.after_request
def add_noindex_headers(response):
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet, noimageindex'
    return response

@app.route('/robots.txt')
def robots_txt():
    return "User-agent: *\nDisallow: /", 200, {'Content-Type': 'text/plain'}

@app.route('/sw.js')
def service_worker():
    response = make_response(app.send_static_file('sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    return response

# ----- Routes / modèles -----
from app import routes, models
from app.models import User


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
