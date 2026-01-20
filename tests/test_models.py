from app.models.models import User, Court, Case, CaseStatus

def test_new_user(init_database):
    """
    GIVEN a User model
    WHEN a new User is created
    THEN check the email, username, and role
    """
    user = User(
        username='testuser',
        password='password',
        name='Test User',
        email='test@test.com',
        tel='0000000000',
        is_admin=False
    )
    assert user.username == 'testuser'
    assert user.email == 'test@test.com'
    assert user.is_admin == False

def test_new_court(init_database):
    """
    GIVEN a Court model
    WHEN a new Court is created
    THEN check the name and active status
    """
    court = Court(name='New Court', is_active=True)
    assert court.name == 'New Court'
    assert court.is_active == True

def test_new_case(init_database):
    """
    GIVEN a Case model
    WHEN a new Case is created
    THEN check the case number and default status
    """
    case = Case(
        case_number='123/2023',
        c_order=1,
        court_id=1,
        status=CaseStatus.active
    )
    assert case.case_number == '123/2023'
    assert case.status == CaseStatus.active
