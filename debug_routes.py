from app import create_app
from extensions import db
from app.models.models import User, Court
from werkzeug.security import generate_password_hash

app = create_app(config_name='testing')

with app.app_context():
    db.create_all()
    
    # Create court and user
    court = Court(name='Test Court', description='Court for testing')
    db.session.add(court)
    db.session.commit()

    user = User(
        username='admin',
        password=generate_password_hash('password'),
        name='Admin User',
        email='admin@example.com',
        tel='1234567890',
        is_admin=True,
        court_id=court.id
    )
    db.session.add(user)
    db.session.commit()

    client = app.test_client()

    print("Testing Login Page GET...")
    response = client.get('/login')
    print(f"Status: {response.status_code}")
    if b"Login" in response.data:
        print("Found 'Login' in response.")
    else:
        print("Did NOT find 'Login' in response.")
    
    print("\nTesting Login POST...")
    response = client.post('/login', data=dict(
        username='admin',
        password='password'
    ), follow_redirects=True)
    print(f"Status: {response.status_code}")
    
    if b"Active Cases" in response.data:
        print("Found 'Active Cases' in response.")
    elif "مدير القضايا".encode('utf-8') in response.data:
        print("Found 'مدير القضايا' in response.")
    else:
        print("Did NOT find expected text in response.")
        print("Response snippet:", response.data[:500]) # Print first 500 bytes

    db.session.remove()
    db.drop_all()
