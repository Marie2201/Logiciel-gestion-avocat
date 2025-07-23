# create_admin.py à la racine
from app import app, db
from app.models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    if not User.query.filter_by(email="admin@cabinet.com").first():
        admin = User(
            nom="Admin",
            role="admin",
            email="admin@cabinet.com",
            password_hash=generate_password_hash("admin123")
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin créé dans :", db.engine.url.database)
    else:
        print("ℹ️ Admin existe déjà.")
