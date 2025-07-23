from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment
from flask_migrate import Migrate # Importe Flask-Migrate ici
from flask_login import LoginManager

app = Flask(__name__)

# --- Configuration de l'application ---
app.config['SECRET_KEY'] = 'secret-key' # À changer pour une vraie clé secrète en production !
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cabinet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True


db = SQLAlchemy(app) 

# 2. CSRF Protection
csrf = CSRFProtect(app)

# 3. Flask-Moment (pour gérer les dates avec Moment.js)
moment = Moment(app)

# 4. Flask-Migrate (pour les migrations de base de données)
migrate = Migrate(app, db) 


# ...
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Le nom de ta fonction de vue pour la connexion
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."

# ...


from app import routes, models
from app.models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


