from flask import Flask
from config import config
from extensions import db, migrate, login_manager, sse


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure runtime directories exist
    import os
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('JSON_STORAGE', 'json_storage'), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # Initialize SSE (Server Sent Events)
    sse_enabled = bool(app.config.get('REDIS_URL'))
    app.config['SSE_ENABLED'] = sse_enabled
    if sse_enabled:
        app.register_blueprint(sse, url_prefix='/stream')


    # Register Blueprints
    from app.blueprints.main import main_bp
    app.register_blueprint(main_bp)

    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.blueprints.cases import cases_bp
    app.register_blueprint(cases_bp)

    from app.blueprints.display import display_bp
    app.register_blueprint(display_bp)

    # Ensure DB tables + default admin exist (dev/prod only)
    # Avoid doing this during tests (tests manage their own DB lifecycle).
    if not app.config.get('TESTING'):
        from werkzeug.security import generate_password_hash
        from app.models.models import User, DisplaySettings, Case

        with app.app_context():
            db.create_all()

            if not User.query.first():
                admin = User(
                    username='admin',
                    password=generate_password_hash('admin123'),
                    name='Administrator',
                    email='admin@example.com',
                    tel='123456789',
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()

            if not DisplaySettings.query.first():
                default_field_map = {
                    'case_number': 'رقم الدعوى',
                    'case_date': 'تاريخ الدعوى',
                    'added_date': 'تاريخ الإضافة',
                    'c_order': 'الترتيب',
                    'next_session_date': 'تاريخ الجلسة القادمة',
                    'session_result': 'نتيجة الجلسة',
                    'num_sessions': 'رقم الجلسة',
                    'case_subject': 'موضوع الدعوى',
                    'defendant': 'المستأنف ضده',
                    'plaintiff': 'المستأنف',
                    'prosecution_number': 'الرقم المقابل',
                    'police_department': 'مركز الشرطة',
                    'police_case_number': 'رقم الشرطة',
                    'status': 'الحالة'
                }
                default_visible = {
                    'case_number',
                    'next_session_date',
                    'case_subject',
                    'plaintiff',
                    'defendant',
                    'status'
                }
                case_fields = [c.name for c in Case.__table__.columns if c.name != 'id']

                for field_name in case_fields:
                    db.session.add(
                        DisplaySettings(
                            field_name=field_name,
                            field_name_ar=default_field_map.get(field_name, field_name.replace('_', ' ')),
                            is_visible=(field_name in default_visible)
                        )
                    )

                db.session.commit()

    from datetime import datetime, timezone

    @app.context_processor
    def inject_now():
        return {
            'now': datetime.now(timezone.utc),
            'sse_enabled': bool(app.config.get('SSE_ENABLED'))
        }

    return app


