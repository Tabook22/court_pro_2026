from flask_login import current_user
from app.models.models import ActivityLog
from extensions import db

def log_activity(action, details=None, case_id=None, court_id=None):
    try:
        activity = ActivityLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            details=details,
            case_id=case_id,
            court_id=court_id
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"Error logging activity: {e}")
        db.session.rollback()
