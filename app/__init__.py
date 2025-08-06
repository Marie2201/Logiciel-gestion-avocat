from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment
from flask_migrate import Migrate
from flask_login import LoginManager
from dotenv import load_dotenv
from flask_mail import Mail, Message

# Chargement des variables d’environnement
load_dotenv()

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# --- Config générale ---
#app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'My-Houda-2025')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True
app.config['SQLALCHEMY_ECHO'] = True
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
# --- Config MAIL ---

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')



MAIL_SERVER = 'sandbox.smtp.mailtrap.io'
MAIL_PORT = 2525
MAIL_USERNAME = 'oumar.sow@avocatshouda.com'





# --- Extensions ---
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
moment = Moment(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
mail = Mail(app)  # ← INIT DIRECTEMENT ICI

# --- Routes et modèles ---
from app import routes, models
from app.models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
