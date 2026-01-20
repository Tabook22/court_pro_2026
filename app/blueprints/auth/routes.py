from flask import render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
from app.models.models import User, Court
from extensions import db, login_manager
from . import auth_bp

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=request.form.get('remember') == 'on')
            flash('Login successful.', 'success')
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.index')
            return redirect(next_page)
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        tel = request.form.get('tel')
        court_id = request.form.get('court_id')
        is_admin = request.form.get('is_admin') == '1'

        if not all([username, password, name, email]):
            flash('Please fill in all required fields (Username, Password, Name, Email).', 'warning')
            return render_template('login.html', courts=courts)
        
        if not is_admin and not court_id:
            flash('Court assignment is required for non-admin users.', 'warning')
            return render_template('login.html', courts=courts)

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or Email already exists. Please choose different ones.', 'danger')
            return render_template('login.html', courts=courts)

        user = User(
            username=username,
            password=generate_password_hash(password),
            name=name,
            email=email,
            tel=tel,
            court_id=court_id if court_id else None,
            is_admin=is_admin
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash(f'User "{username}" registered successfully. Please login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')

    return render_template('login.html', courts=courts)

@auth_bp.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    if not current_user.is_admin:
         flash('You do not have permission to register new users.', 'danger')
         return redirect(url_for('main.index'))

    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        tel = request.form.get('tel')
        court_id = request.form.get('court_id')
        is_admin = request.form.get('is_admin') == 'on'

        if not all([username, password, name, email]):
            flash('Please fill in all required fields (Username, Password, Name, Email).', 'warning')
            return render_template('add_user.html', courts=courts,
                                   username=username, name=name, email=email, tel=tel, is_admin=is_admin)
        
        if not is_admin and not court_id:
            flash('Court assignment is required for non-admin users.', 'warning')
            return render_template('add_user.html', courts=courts,
                                   username=username, name=name, email=email, tel=tel, is_admin=is_admin)

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or Email already exists. Please choose different ones.', 'danger')
            return render_template('add_user.html', courts=courts,
                                   username=username, name=name, email=email, tel=tel, is_admin=is_admin)

        user = User(
            username=username,
            password=generate_password_hash(password),
            name=name,
            email=email,
            tel=tel,
            court_id=court_id if court_id else None,
            is_admin=is_admin
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash(f'User "{username}" registered successfully.', 'success')
            return redirect(url_for('auth.list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')

    return render_template('add_user.html', courts=courts)

@auth_bp.route('/users')
@login_required
def list_users():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    users = User.query.order_by(User.name).all()
    return render_template('users.html', users=users)

@auth_bp.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    return redirect(url_for('auth.admin_add_user'))

@auth_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('auth.list_users'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))
    
    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if username != user.username:
             if not username:
                  flash('Username cannot be empty.', 'danger')
                  return render_template('edit_user.html', user=user)
             if User.query.filter(User.username == username, User.id != user_id).first():
                  flash('Username already exists.', 'danger')
                  return render_template('edit_user.html', user=user)
             user.username = username

        if email != user.email:
             if not email:
                  flash('Email cannot be empty.', 'danger')
                  return render_template('edit_user.html', user=user)
             if User.query.filter(User.email == email, User.id != user_id).first():
                  flash('Email already exists.', 'danger')
                  return render_template('edit_user.html', user=user)
             user.email = email

        if password:
            user.password = generate_password_hash(password)

        new_court_id = request.form.get('court_id')
        if new_court_id:
            user.court_id = int(new_court_id)
        elif not request.form.get('is_admin'):
            flash('Court assignment is required for non-admin users.', 'warning')
            return render_template('edit_user.html', user=user, courts=courts)

        user.name = request.form.get('name', user.name)
        user.tel = request.form.get('tel', user.tel)
        
        is_potentially_removing_last_admin = (
             user.is_admin and
             request.form.get('is_admin') != 'on' and
             User.query.filter_by(is_admin=True).count() == 1 and
             user.id == current_user.id
        )
        if is_potentially_removing_last_admin:
             flash('Cannot remove admin rights from the last administrator.', 'danger')
             return render_template('edit_user.html', user=user)

        user.is_admin = request.form.get('is_admin') == 'on'

        try:
            db.session.commit()
            flash(f'User "{user.username}" updated successfully.', 'success')
            return redirect(url_for('auth.list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')

    return render_template('edit_user.html', user=user, courts=courts)

@auth_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
    elif user.is_admin and User.query.filter_by(is_admin=True).count() == 1:
         flash('Cannot delete the last administrator account.', 'danger')
    else:
        try:
            username = user.username
            db.session.delete(user)
            db.session.commit()
            flash(f'User "{username}" deleted successfully.', 'success')
        except Exception as e:
             db.session.rollback()
             flash(f'Error deleting user: {str(e)}', 'danger')

    return redirect(url_for('auth.list_users'))

@auth_bp.route('/list_users_info')
@login_required
def list_users_info():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    users = User.query.order_by(User.username).all()
    user_list = [{"username": user.username, "name": user.name} for user in users]
    return jsonify(user_list)

@auth_bp.route('/impersonate_user/<int:user_id>')
@login_required
def impersonate_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.index'))
    
    user_to_impersonate = db.session.get(User, user_id)
    if not user_to_impersonate:
        flash('User not found.', 'danger')
        return redirect(url_for('auth.list_users'))
    
    session['original_admin_id'] = current_user.id
    session['impersonating'] = True
    
    logout_user()
    login_user(user_to_impersonate)
    
    flash(f'You are now impersonating {user_to_impersonate.name} ({user_to_impersonate.username})', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/stop_impersonation')
@login_required
def stop_impersonation():
    if not session.get('impersonating'):
        flash('You are not currently impersonating another user.', 'warning')
        return redirect(url_for('main.index'))
    
    original_admin_id = session.get('original_admin_id')
    if not original_admin_id:
        flash('Cannot restore original session.', 'danger')
        return redirect(url_for('auth.login'))
    
    original_admin = db.session.get(User, original_admin_id)
    if not original_admin:
        flash('Original admin user not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    session.pop('original_admin_id', None)
    session.pop('impersonating', None)
    
    logout_user()
    login_user(original_admin)
    
    flash('Impersonation ended. You are back to your admin account.', 'success')
    return redirect(url_for('main.list_courts'))
