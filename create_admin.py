# create_admin.py à la racine
from app import app, db
from app.models import User
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
import os

load_dotenv()

email = os.getenv('ADMIN_EMAIL')
password = os.getenv('ADMIN_PASSWORD')


with app.app_context():
    if not User.query.filter_by(email=email).first():
        admin = User(
            nom="Admin",
            role="admin",
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin créé dans :", db.engine.url.database)
    else:
        print("ℹ️ Admin existe déjà.")
