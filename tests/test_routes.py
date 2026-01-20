def test_login_page(client):
    """
    GIVEN a Flask application
    WHEN the '/login' page is requested (GET)
    THEN check that the response is valid
    """
    response = client.get('/login')
    assert response.status_code == 200
    assert b"Login" in response.data or "تسجيل الدخول".encode('utf-8') in response.data
    
def test_index_page_redirect(client):
    """
    GIVEN a Flask application
    WHEN the '/' page is requested (GET) without login
    THEN check that it redirects to login
    """
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    # Should be on login page now
    assert b"Login" in response.data or "تسجيل الدخول".encode('utf-8') in response.data

def test_login_post(client, init_database):
    """
    GIVEN a registered user
    WHEN valid login credentials are posted
    THEN check that the user is logged in
    """
    response = client.post('/login', data=dict(
        username='admin',
        password='password'
    ), follow_redirects=True)
    assert response.status_code == 200
    # Should be on dashboard/index
    assert b"Active Cases" in response.data or "مدير القضايا".encode('utf-8') in response.data
