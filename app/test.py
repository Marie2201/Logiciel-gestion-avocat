from app import db
from app.models import Notification
from datetime import datetime
n = Notification(user_id=7, title='Test', message='Ping', is_read=False, created_at=datetime.utcnow())
db.session.add(n); db.session.commit()
