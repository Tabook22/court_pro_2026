import pytest
from app import create_app
from extensions import db
from config import TestingConfig
from app.models.models import User, Court

@pytest.fixture(scope='module')
def app():
    app = create_app(config_name='testing')
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='module')
def client(app):
    return app.test_client()

@pytest.fixture(scope='module')
def init_database(app):
    # Create default court and admin user for testing
    court = Court(name='Test Court', description='Court for testing')
    db.session.add(court)
    db.session.commit()

    user = User(
        username='admin',
        password='scrypt:32768:8:1$k7X...', # Mocked hash or use generate_password_hash
        name='Admin User',
        email='admin@example.com',
        tel='1234567890',
        is_admin=True,
        court_id=court.id
    )
    # Note: In real tests, import generate_password_hash and use it
    from werkzeug.security import generate_password_hash
    user.password = generate_password_hash('password')
    
    db.session.add(user)
    db.session.commit()

    yield db

    db.session.remove()
    db.drop_all()
