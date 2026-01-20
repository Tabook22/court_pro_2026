# Salalah, Oman - March 29, 2025
import os
import json
import time
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_from_directory, session
)
from models.models import db, Court, Case, User, CaseStatus, DisplayCase, DisplaySettings
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import urlparse # <-- CORRECTED IMPORT (Changed from werkzeug.urls)
from datetime import datetime, timezone, date, timedelta
from sqlalchemy import extract
from collections import defaultdict
from flask_migrate import Migrate
from models.models import db, CaseStatus  # Import db from models
# Assuming excel_processor.py contains your ExcelProcessor class
from excel_processor import ExcelProcessor
from flask_sse import sse
import redis # Import redis if using it

# --- Placeholder for JsonToDatabase ---
# You should have this logic in a separate file (e.g., json_to_db.py) and import it.
# This is a placeholder based on how the import route uses it.
class JsonToDatabase:
    def __init__(self, db_session, court_id):
        self.db = db_session
        self.court_id = court_id
        self.json_storage_path = app.config.get('JSON_STORAGE', 'json_storage') # Get from app config

    def process_json_file(self, json_filename):
        """Reads the JSON file and returns the list of case data dictionaries."""
        json_path = os.path.join(self.json_storage_path, json_filename)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Assuming the structure is {'schema': {...}, 'data': [...]}
                return data.get('data', [])
        except FileNotFoundError:
            print(f"Error: JSON file not found at {json_path}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {json_path}")
            return None
        except Exception as e:
            print(f"Error reading JSON file {json_path}: {str(e)}")
            return None

    def import_data(self, case_data_list):
        """Imports data into the database, skipping duplicates based on case_number."""
        cases_added_count = 0
        skipped_cases = []
        errors = []

        if not case_data_list:
            errors.append("No data found in the JSON file to import.")
            return {'success': False, 'cases_added': 0, 'skipped': [], 'errors': errors}

        # Get existing case numbers for this court only
        try:
            existing_case_numbers = {
                case.case_number for case in Case.query.filter_by(court_id=self.court_id).with_entities(Case.case_number).all()
            }
        except Exception as e:
            errors.append(f"Database error fetching existing cases: {str(e)}")
            return {'success': False, 'cases_added': 0, 'skipped': [], 'errors': errors}


        for idx, record in enumerate(case_data_list):
            row_num = idx + 1 # User-friendly row number
            case_number = record.get('case_number')

            if not case_number:
                error_msg = f"Row {row_num}: Missing 'case_number'."
                errors.append(error_msg)
                skipped_cases.append({'row': row_num, 'reason': 'Missing case_number', 'data': record})
                continue # Skip this record

            # --- Skip if case_number already exists ---
            if str(case_number) in existing_case_numbers:
                # Update existing case instead of skipping
                try:
                    existing_case = Case.query.filter_by(case_number=str(case_number), court_id=self.court_id).first()
                    if existing_case:
                        # Update case fields
                        existing_case.case_date = case_date_obj
                        existing_case.next_session_date = str(record.get('next_session_date', '')) if record.get('next_session_date') else None
                        existing_case.session_result = str(record.get('session_result', ''))
                        existing_case.num_sessions = num_sessions
                        existing_case.case_subject = str(record.get('case_subject', 'N/A'))
                        existing_case.defendant = str(record.get('defendant', 'N/A'))
                        existing_case.plaintiff = str(record.get('plaintiff', 'N/A'))
                        existing_case.prosecution_number = str(record.get('prosecution_number', ''))
                        existing_case.police_department = str(record.get('police_department', ''))
                        existing_case.police_case_number = str(record.get('police_case_number', ''))
                        existing_case.status = status_enum
                        cases_added_count += 1
                        continue
                except Exception as e:
                    errors.append(f"Error updating existing case {case_number}: {str(e)}")
                    skipped_cases.append({'row': row_num, 'reason': f'Error updating: {str(e)}', 'case_number': case_number})
                    continue

            try:
                # --- Create new Case object ---
                # Validate and convert data types carefully
                case_date_str = record.get('case_date')
                case_date_obj = None
                if case_date_str:
                    try:
                        # Adjust format '%Y-%m-%d' if your JSON uses a different one
                        case_date_obj = datetime.strptime(str(case_date_str), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        errors.append(f"Row {row_num} (Case# {case_number}): Invalid case_date format '{case_date_str}'. Skipping.")
                        skipped_cases.append({'row': row_num, 'reason': 'Invalid case_date', 'case_number': case_number, 'value': case_date_str})
                        continue # Skip if date is crucial and invalid

                # Handle status - default to inactive if missing or invalid
                status_str = record.get('status', 'inactive')
                try:
                    # Ensure status string exactly matches enum value (e.g., 'in session')
                    status_enum = CaseStatus(str(status_str).lower())
                except ValueError:
                    errors.append(f"Row {row_num} (Case# {case_number}): Invalid status value '{status_str}'. Defaulting to inactive.")
                    status_enum = CaseStatus.inactive # Default to inactive

                # Get integer fields with defaults and error handling
                try:
                    c_order = int(record.get('c_order', 9999)) # Default order if missing
                except (ValueError, TypeError):
                     errors.append(f"Row {row_num} (Case# {case_number}): Invalid c_order value. Using default 9999.")
                     c_order = 9999

                try:
                    num_sessions = int(record.get('num_sessions', 1)) # Default 1 if missing
                except (ValueError, TypeError):
                     errors.append(f"Row {row_num} (Case# {case_number}): Invalid num_sessions value. Using default 1.")
                     num_sessions = 1

                # Add other fields similarly, converting types and handling potential errors/defaults
                new_case = Case(
                    case_number=str(case_number), # Ensure string
                    case_date=case_date_obj, # Use converted date
                    c_order=c_order,
                    court_id=self.court_id, # Use the court_id passed during initialization
                    user_id=current_user.id, # Add user_id for tracking who imported
                    next_session_date=str(record.get('next_session_date', '')) if record.get('next_session_date') else None, # Handle None/empty string for date
                    session_result=str(record.get('session_result', '')),
                    num_sessions=num_sessions,
                    case_subject=str(record.get('case_subject', 'N/A')),
                    defendant=str(record.get('defendant', 'N/A')),
                    plaintiff=str(record.get('plaintiff', 'N/A')),
                    prosecution_number=str(record.get('prosecution_number', '')),
                    police_department=str(record.get('police_department', '')),
                    police_case_number=str(record.get('police_case_number', '')),
                    status=status_enum, # Use validated enum
                    # added_date is handled by default in model
                )
                self.db.add(new_case)
                cases_added_count += 1
                # Add the new case number to our set to prevent duplicates *within the same file*
                existing_case_numbers.add(str(case_number))

            except KeyError as e:
                error_msg = f"Row {row_num} (Case# {case_number}): Missing expected field '{e}'."
                errors.append(error_msg)
                skipped_cases.append({'row': row_num, 'reason': f'Missing field: {e}', 'case_number': case_number})
            except ValueError as e:
                error_msg = f"Row {row_num} (Case# {case_number}): Invalid data type for a field. Error: {e}."
                errors.append(error_msg)
                skipped_cases.append({'row': row_num, 'reason': f'Invalid data type: {e}', 'case_number': case_number})
            except Exception as e:
                # Catch any other unexpected errors during record processing
                error_msg = f"Row {row_num} (Case# {case_number}): Unexpected error: {str(e)}."
                errors.append(error_msg)
                skipped_cases.append({'row': row_num, 'reason': f'Unexpected error: {str(e)}', 'case_number': case_number})
                # Consider rolling back immediately or collecting all errors first
                # self.db.rollback() # Option: Rollback per record error

        try:
            self.db.commit()
            return {
                'success': True,
                'cases_added': cases_added_count,
                'skipped': skipped_cases,
                'errors': errors
            }
        except Exception as e:
            self.db.rollback()
            errors.append(f"Database commit failed: {str(e)}")
            # Add previously added count to skipped count as they were rolled back
            final_skipped = skipped_cases + [{'row': 'N/A', 'reason': 'Rolled back during commit', 'count': cases_added_count}]
            return {
                'success': False,
                'cases_added': 0, # Reset count as commit failed
                'skipped': final_skipped,
                'errors': errors
            }
# --- End Placeholder ---


# === Flask App Configuration ===
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key-only-for-dev') # Use environment variable
# Determine base directory for the database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL',
                                                      'sqlite:///' + os.path.join(basedir, 'mydb.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_STORAGE'] = os.path.join(basedir, 'json_storage') # Store JSON in instance subfolder
UPLOAD_FOLDER = os.path.join(basedir, 'uploads') # Store uploads in instance subfolder
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize extensions
db.init_app(app)


# --- Flask-SSE Configuration ---
# Option 2: Using In-Memory (Simpler, works without Redis on Replit)
# This is more suitable for single-process deployment on Replit
app.config["REDIS_URL"] = "redis://localhost"  # This will fall back to in-memory

# Register the SSE blueprint
app.register_blueprint(sse, url_prefix='/stream')


# Ensure the upload and JSON storage folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(app.config['JSON_STORAGE'], exist_ok=True)

# === Database and Migration Setup ===
from models import db
migrate = Migrate(app, db)

# === Login Manager Setup ===
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redirect to /login if @login_required fails
login_manager.login_message_category = 'info' # Bootstrap class for flash message

# === Database Models ===
# Import models from models.py
from models.models import User, Case, CaseStatus, DisplayCase, DisplaySettings, ActivityLog

# Removed duplicate DisplaySettings class since it's imported from models.py


# === Flask-Login User Loader ===
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except ValueError:
        return None

# === Context Processors ===
@app.context_processor
def utility_processor():
    # Provides 'now' variable to all templates
    return {'now': datetime.now(timezone.utc)}

# === Activity Logging Functions ===

# Helper function to log activities
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

# === Routes ===

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    if current_user.is_admin:
        users_count = User.query.count()
        cases_count = Case.query.count()
        users = User.query.all()
        cases = Case.query.all()
        return render_template('control.html', users=users, cases=cases)
    else:
        if not current_user.court_id:
            flash('No court assigned to your account.', 'danger')
            return redirect(url_for('login'))

        # Get court-specific stats
        court_cases = Case.query.filter_by(court_id=current_user.court_id).order_by(Case.added_date.desc()).all()
        active_cases = [case for case in court_cases if case.status == CaseStatus.active]
        display_cases = DisplayCase.query.join(Case).filter(Case.court_id == current_user.court_id).all()

        # Get latest imported cases (last 10)
        latest_cases = court_cases[:10]

        return render_template('user_dashboard.html', 
                             cases=court_cases,
                             active_cases=active_cases,
                             display_cases=display_cases,
                             latest_cases=latest_cases,
                             court=current_user.court)


# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user, remember=request.form.get('remember') == 'on') # Correct remember handling
            flash('Login successful.', 'success')
            next_page = request.args.get('next')
            # Prevent open redirect vulnerability - Use urlparse from urllib.parse here
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('index')
            return redirect(next_page)
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html') # Create a login.html template

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- Registration Route (Admin Only) ---
# Public registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        tel = request.form.get('tel')
        court_id = request.form.get('court_id')
        is_admin = request.form.get('is_admin') == '1' # Check for '1' value

        # Basic Validation
        if not all([username, password, name, email]):
            flash('Please fill in all required fields (Username, Password, Name, Email).', 'warning')
            return render_template('login.html', courts=courts)
        
        # Validate court assignment for non-admin users
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
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')

    # For GET request, render the login template with registration tab
    return render_template('login.html', courts=courts)

# Admin-only route for adding users
@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    # Only allow admins to register new users
    if not current_user.is_admin:
         flash('You do not have permission to register new users.', 'danger')
         return redirect(url_for('index'))

    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        tel = request.form.get('tel')
        court_id = request.form.get('court_id')
        is_admin = request.form.get('is_admin') == 'on' # Checkbox value

        # Basic Validation
        if not all([username, password, name, email]):
            flash('Please fill in all required fields (Username, Password, Name, Email).', 'warning')
            return render_template('add_user.html', courts=courts,
                                   username=username, name=name, email=email, tel=tel, is_admin=is_admin)
        
        # Validate court assignment for non-admin users
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
            return redirect(url_for('list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')

    # For GET request, render the registration form with courts list
    return render_template('add_user.html', courts=courts)

# --- File Upload and Processing Routes ---
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if not current_user.is_authenticated:
         return jsonify({'success': False, 'message': 'Permission denied'}), 403

    # Check if user has court assignment (allow admin impersonation)
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    if 'excelFile' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400

    file = request.files['excelFile']

    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if file and file.filename.lower().endswith(('.xls', '.xlsx')):
        current_date = datetime.now()
        year_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(current_date.year))
        month_folder = os.path.join(year_folder, current_date.strftime('%m-%B')) # e.g., 03-March
        date_folder = os.path.join(month_folder, current_date.strftime('%d')) # e.g., 29

        os.makedirs(date_folder, exist_ok=True)

        timestamp = int(time.time())
        _, file_extension = os.path.splitext(file.filename)
        # Use secure_filename on the original filename *before* adding timestamp for safety
        safe_base = secure_filename(os.path.splitext(file.filename)[0])
        # Handle cases where secure_filename returns empty string
        if not safe_base:
             safe_base = "uploaded_file"
        # Add court ID prefix to filename
        court_prefix = f"court_{current_user.court_id}_"
        new_filename = f"{court_prefix}{safe_base}_{timestamp}{file_extension}"

        file_path = os.path.join(date_folder, new_filename)

        try:
             file.save(file_path)
             return jsonify({'success': True, 'message': f'File "{file.filename}" uploaded successfully as {new_filename}'}), 200
        except Exception as e:
             return jsonify({'success': False, 'message': f'Error saving file: {str(e)}'}), 500
    else:
        return jsonify({'success': False, 'message': 'Invalid file type. Only .xls and .xlsx are allowed.'}), 400

@app.route('/list_files')
@login_required
def list_files():
    """
    Lists uploaded files, structured by year and month, with sorting.
    Filters files by user's court unless user is admin.
    """
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    def is_file_accessible(filename):
        """Check if file belongs to user's court"""
        if current_user.is_admin:
            return True
        court_prefix = f"court_{current_user.court_id}_"
        return filename.startswith(court_prefix)

    # Use defaultdict for easier nested structure creation
    # Structure: { year(str): list[ tuple(month_str, list[file_rel_path_str]) ] }
    files_data_sorted = defaultdict(list)
    upload_root = app.config['UPLOAD_FOLDER']

    if not os.path.exists(upload_root):
        flash(f"Upload directory '{upload_root}' not found.", 'warning')
        # Pass an empty dict to the template so it shows "No files found"
        return render_template('list_files.html', files_by_year_month_sorted={})

    try:
        # Get and sort years (assuming year folders are digits), descending
        years = sorted(
            [d for d in os.listdir(upload_root) if os.path.isdir(os.path.join(upload_root, d)) and d.isdigit()],
            key=int,
            reverse=True
        )
    except OSError as e:
        print(f"Error reading upload root directory {upload_root}: {e}")
        flash(f"Error accessing upload directory: {e}", 'danger')
        return render_template('list_files.html', files_by_year_month_sorted={})

    # Process each year
    for year in years:
        year_path = os.path.join(upload_root, year)
        temp_month_files = defaultdict(list) # Temp dict for current year's months {month_str: list[files]}

        try:
            # Get month directories for the current year
            month_dirs = [d for d in os.listdir(year_path) if os.path.isdir(os.path.join(year_path, d))]
        except OSError as e:
            print(f"Error reading year directory {year_path}: {e}")
            continue # Skip this year if unreadable

        # Process each month within the year
        for month in month_dirs:
            month_path = os.path.join(year_path, month)
            try:
                # Get and sort day directories (assuming digits), descending
                days = sorted(
                    [d for d in os.listdir(month_path) if os.path.isdir(os.path.join(month_path, d)) and d.isdigit()],
                    key=int,
                    reverse=True
                )
            except OSError as e:
                print(f"Error reading month directory {month_path}: {e}")
                continue # Skip this month if unreadable

            # Process each day within the month
            for day in days:
                day_path = os.path.join(month_path, day)
                try:
                    # Get and sort files alphabetically, filtering by court
                    files = sorted([f for f in os.listdir(day_path) 
                                  if os.path.isfile(os.path.join(day_path, f)) and is_file_accessible(f)])
                    if files:
                        # Store relative path: day/filename.ext
                        temp_month_files[month].extend([os.path.join(day, file) for file in files])
                    else:
                        # Attempt to remove empty day folder (optional cleanup)
                        try:
                            os.rmdir(day_path)
                            print(f"Cleaned up empty folder: {day_path}")
                        except OSError as e_rm:
                            # Ignore error if directory not empty or other issue
                            print(f"Could not remove allegedly empty folder {day_path}: {e_rm}")
                except Exception as e:
                    print(f"Error listing or processing files in {day_path}: {e}")

            # Attempt to remove empty month folder (optional cleanup)
            try:
                if os.path.exists(month_path) and not os.listdir(month_path):
                    os.rmdir(month_path)
                    print(f"Cleaned up empty folder: {month_path}")
            except OSError as e_rm:
                 print(f"Could not remove allegedly empty folder {month_path}: {e_rm}")

        # *** Sort the collected months for the current year ***
        if temp_month_files:
            def sort_key_month(month_item_tuple):
                """Sort key for month strings like '03-March', '10-October'."""
                month_str = month_item_tuple[0] # Get the month string (key)
                if '-' in month_str and month_str.split('-')[0].isdigit():
                    return int(month_str.split('-')[0])
                else:
                    return 0 # Default for unexpected formats, adjust as needed

            sorted_month_items_list = sorted(
                temp_month_files.items(), # Get list of (month_str, files_list) tuples
                key=sort_key_month,
                reverse=True # Show latest months first
            )
            # Assign the sorted list to the final dictionary for this year
            files_data_sorted[year] = sorted_month_items_list

        # Attempt to remove empty year folder (optional cleanup)
        try:
             if os.path.exists(year_path) and not os.listdir(year_path):
                 os.rmdir(year_path)
                 print(f"Cleaned up empty folder: {year_path}")
        except OSError as e_rm:
             print(f"Could not remove allegedly empty folder {year_path}: {e_rm}")


    # Pass the final, structured, and sorted data to the template
    # The template should expect dict[year] = list[tuple(month, list[files])]
    return render_template('list_files.html', files_by_year_month_sorted=files_data_sorted)


@app.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    year = request.form.get('year')
    month = request.form.get('month')
    # File path received might include the day directory, e.g., "29/myfile_12345.xlsx"
    file_rel_path = request.form.get('file')

    if not all([year, month, file_rel_path]):
        return jsonify({'success': False, 'message': 'Invalid file information provided'}), 400

    # Construct the full path relative to the UPLOAD_FOLDER root
    # Sanitize path components to prevent directory traversal vulnerabilities
    year = secure_filename(year)
    month = secure_filename(month)
    # Split relative path safely
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts): # Double check secure_filename results
         return jsonify({'success': False, 'message': 'Invalid file path component detected'}), 400
    safe_rel_path = os.path.join(*safe_parts) # Rejoin using OS separator

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], year, month, safe_rel_path)
    # Get directory paths AFTER constructing the full path
    day_folder = os.path.dirname(file_path)
    month_folder = os.path.dirname(day_folder)
    year_folder = os.path.dirname(month_folder)


    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            os.remove(file_path)
            # Attempt to remove parent folders if they become empty
            # Check existence before attempting listdir/rmdir
            if os.path.exists(day_folder) and not os.listdir(day_folder):
                os.rmdir(day_folder)
                if os.path.exists(month_folder) and not os.listdir(month_folder):
                    os.rmdir(month_folder)
                    if os.path.exists(year_folder) and not os.listdir(year_folder):
                        os.rmdir(year_folder)
            return jsonify({'success': True, 'message': 'File deleted successfully'}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error deleting file or cleanup: {str(e)}'}), 500
    else:
        print(f"Delete failed: File not found at {file_path}") # Log expected path
        return jsonify({'success': False, 'message': 'File not found'}), 404


@app.route('/view_file/<year>/<month>/<path:file_rel_path>')
@login_required
def view_file(year, month, file_rel_path):
    # Sanitize path components robustly
    year = secure_filename(year)
    month = secure_filename(month)
    # Secure the relative path components individually
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts):
         return "Invalid path component", 400

    directory = os.path.join(app.config['UPLOAD_FOLDER'], year, month, *safe_parts[:-1]) # All parts except filename
    filename = safe_parts[-1] # Last part is filename

    # Basic check: Ensure the directory is within the intended UPLOAD_FOLDER
    if not os.path.abspath(directory).startswith(os.path.abspath(app.config['UPLOAD_FOLDER'])):
         return "Access denied", 403

    try:
        return send_from_directory(directory, filename, as_attachment=False) # View in browser if possible
    except FileNotFoundError:
        return "File not found", 404
    except Exception as e:
         print(f"Error serving file {directory}/{filename}: {e}")
         return "Error serving file", 500


@app.route('/process_excel', methods=['POST'])
@login_required
def process_excel():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    year = request.form.get('year')
    month = request.form.get('month')
    file_rel_path = request.form.get('file') # e.g., "29/myfile_12345.xlsx"

    if not all([year, month, file_rel_path]):
        return jsonify({'success': False, 'message': 'Invalid file information provided'}), 400

    # Sanitize and construct path
    year = secure_filename(year)
    month = secure_filename(month)
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts):
         return jsonify({'success': False, 'message': 'Invalid file path component detected'}), 400
    safe_rel_path = os.path.join(*safe_parts)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], year, month, safe_rel_path)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found'}), 404

    # Initialize processor (pass storage path from app config)
    processor = ExcelProcessor(json_storage_path=app.config['JSON_STORAGE'])
    result = processor.process_excel_file(file_path) # Process the file

    if result.get('success'):
        # Return success and necessary info for the next step (import)
        return jsonify({            'success': True,
            'message': result.get('message', 'File processed successfully.'),
            'schema': result.get('schema'),
            'json_filename': result.get('json_filename') # Crucial for the import step
        })
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', 'Error processing file.'),
            'error': result.get('error')
        }), 500 # Use 500 for server-side processing errors

@app.route('/processed_json/<filename>')
@login_required
def serve_processed_json(filename):
    # Sanitize filename
    filename = secure_filename(filename)
    if '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400
    try:
        return send_from_directory(app.config['JSON_STORAGE'], filename)
    except FileNotFoundError:
        return "JSON file not found", 404


# --- IMPORT ROUTE (ENHANCED) ---
@app.route('/import_to_database', methods=['POST'])
@login_required
def import_to_database():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    json_filename = request.form.get('json_filename')
    if not json_filename:
        return jsonify({'success': False, 'message': 'No JSON file specified'}), 400

    # Sanitize filename
    json_filename = secure_filename(json_filename)
    if '..' in json_filename or json_filename.startswith('/'):
        return jsonify({'success': False, 'message': 'Invalid JSON filename'}), 4000

    try:
        # Pass both db.session and current user's court_id
        importer = JsonToDatabase(db.session, current_user.court_id)
        case_data_list = importer.process_json_file(json_filename)

        if case_data_list is None: # Check if file reading/parsing failed
            return jsonify({'success': False, 'message': f'Failed to read or parse JSON file: {json_filename}'}), 500

        # Perform the import logic (including duplicate check)
        result = importer.import_data(case_data_list) # Use the import_data method

        # Construct user-friendly message
        message = f"Import completed. Cases added: {result.get('cases_added', 0)}."
        skipped_count = len(result.get('skipped', []))
        error_count = len(result.get('errors', [])) # Count actual errors logged

        if skipped_count > 0:
            message += f" Records skipped: {skipped_count} (Duplicates or data issues)."
            # Log skipped details to server console for admin review
            print(f"Skipped records during import of {json_filename}: {result.get('skipped', [])}")
        if error_count > 0:
             message += f" Errors encountered: {error_count}."
             print(f"Errors during import of {json_filename}: {result.get('errors', [])}")


        return jsonify({
            'success': result.get('success', False),
            'message': message,
            'cases_added': result.get('cases_added', 0),
            'skipped_count': skipped_count,
            'error_count': error_count,
            # Optionally return details if needed, but can be large
            # 'skipped_details': result.get('skipped'),
            # 'error_details': result.get('errors')
        })

    except Exception as e:
        # General exception handler for the route
        print(f"Exception during import route execution for {json_filename}: {str(e)}")
        import traceback
        print(traceback.format_exc()) # Log full traceback for debugging
        return jsonify({
            'success': False,
            'message': f'An unexpected server error occurred during the import process.'
        }), 500

# --- Case Management Routes ---
@app.route('/cases')
@login_required
def list_cases():
    try:
        sort_by = request.args.get('sort_by', 'all')  # Default to 'all' to show all cases
        selected_date = request.args.get('date')  # Don't default to today
        selected_month = request.args.get('month')  # Format: YYYY-MM
        selected_year = request.args.get('year')
        case_number_search = request.args.get('case_number')
        
        # Base query
        if current_user.is_admin:
            query = Case.query.join(Court).join(User)
        else:
            if not current_user.court_id:
                flash('No court assigned to your account.', 'danger')
                return redirect(url_for('index'))
            query = Case.query.filter(
                (Case.court_id == current_user.court_id) & 
                (Case.user_id == current_user.id)
            )

        # Apply date filtering - prioritize specific filters over sort_by
        today = datetime.now().date()
        filter_applied = False
        
        if selected_date:
            try:
                filter_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
                query = query.filter(Case.case_date == filter_date)
                filter_applied = True
            except ValueError:
                flash('Invalid date format', 'warning')
        
        elif selected_month:
            try:
                year, month = map(int, selected_month.split('-'))
                query = query.filter(
                    extract('year', Case.case_date) == year,
                    extract('month', Case.case_date) == month
                )
                filter_applied = True
            except ValueError:
                flash('Invalid month format', 'warning')
        
        elif selected_year:
            try:
                year = int(selected_year)
                query = query.filter(extract('year', Case.case_date) == year)
                filter_applied = True
            except ValueError:
                flash('Invalid year format', 'warning')
        
        elif case_number_search:
            query = query.filter(Case.case_number.ilike(f'%{case_number_search}%'))
            filter_applied = True
        
        # Only apply sort_by filters if no specific date filter was applied
        elif not filter_applied and sort_by != 'all':
            if sort_by == 'day':
                query = query.filter(Case.case_date == today)
            elif sort_by == 'week':
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=6)
                query = query.filter(Case.case_date.between(week_start, week_end))
            elif sort_by == 'month':
                query = query.filter(
                    extract('year', Case.case_date) == today.year,
                    extract('month', Case.case_date) == today.month
                )
            elif sort_by == 'year':
                query = query.filter(extract('year', Case.case_date) == today.year)

        cases = query.order_by(Case.case_date.desc(), Case.c_order.asc()).all()

        # Get the list of all possible CaseStatus enum members
        status_options = list(CaseStatus)

        # Render the template, passing both cases and status options
        return render_template(
            'cases.html',
            cases=cases,
            status_options=status_options
        )
    except Exception as e:
        # Log the error for debugging
        print(f"Error fetching data for /cases: {e}")
        import traceback
        print(traceback.format_exc())
        flash("An error occurred while loading the cases page.", "danger")
        return redirect(url_for('index')) # Redirect to a safe page on error

@app.route('/add_case', methods=['GET', 'POST'])
@login_required
def add_case():
    # Check if user has court assignment or is admin
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))
    
    # If admin without court assignment, show message
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to add cases.', 'info')
        return redirect(url_for('list_users'))

    if request.method == 'POST':
        # Find the highest current order to append the new case
        highest_order = db.session.query(db.func.max(Case.c_order)).scalar()
        next_order = 1 if highest_order is None else highest_order + 1

        # Validate case_number uniqueness
        case_number = request.form.get('case_number')
        if not case_number:
             flash('Case Number is required.', 'danger')
             return render_template('add_case.html', form_data=request.form) # Pass back form data
        if Case.query.filter_by(case_number=case_number).first():
             flash(f'Case Number "{case_number}" already exists.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        # Validate and convert date
        try:
            case_date_str = request.form.get('case_date')
            case_date = datetime.strptime(case_date_str, '%Y-%m-%d').date() if case_date_str else None
        except ValueError:
             flash('Invalid Case Date format. Please use YYYY-MM-DD.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        # Validate number of sessions
        try:
             num_sessions = int(request.form.get('num_sessions', 1))
             if num_sessions < 0: raise ValueError("Cannot be negative")
        except (ValueError, TypeError):
             flash('Invalid Number of Sessions. Please enter a valid non-negative integer.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        # Get status, default to 'inactive'
        status_str = request.form.get('status', 'inactive') # 'status' here might come from a hidden field or default
        try:
            # If status comes from the checkbox in add_case.html, it sends 'active' when checked
            if 'status_checkbox' in request.form and request.form['status_checkbox'] == 'active':
                 status_enum = CaseStatus.active
            else:
                 status_enum = CaseStatus.inactive # Default if checkbox not checked/present
        except ValueError:
             status_enum = CaseStatus.inactive # Fallback

        try:
            case = Case(
                case_number=case_number,
                case_date=case_date,
                c_order=next_order,
                # Ensure next_session_date is handled correctly (string or date?)
                next_session_date=request.form.get('next_session_date') or None, # Store None if empty
                session_result=request.form.get('session_result'),
                num_sessions=num_sessions,
                case_subject=request.form.get('case_subject'),
                defendant=request.form.get('defendant'),
                plaintiff=request.form.get('plaintiff'),
                prosecution_number=request.form.get('prosecution_number'),
                police_department=request.form.get('police_department'),
                police_case_number=request.form.get('police_case_number'),
                status=status_enum,
                court_id=current_user.court_id, # Add court_id here
                user_id=current_user.id # Ensure the case is linked to the user adding it
            )
            db.session.add(case)
            db.session.commit()
            
            # Log activity
            log_activity(
                action='Case Added',
                details=f'Added case {case_number}: {case.case_subject}',
                case_id=case.id,
                court_id=current_user.court_id
            )
            
            flash(f'Case "{case.case_number}" added successfully.', 'success')
            return redirect(url_for('list_cases'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding case: {str(e)}', 'danger')
            return render_template('add_case.html', form_data=request.form) # Show form again with error

    # GET request
    return render_template('add_case.html')


@app.route('/edit_case/<int:case_id>', methods=['GET', 'POST'])
@login_required
def edit_case(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('list_cases'))

    # Use session.get for primary key lookup
    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found.', 'danger')
        return redirect(url_for('list_cases'))

    if request.method == 'POST':
        # Validate case_number uniqueness IF it changed
        new_case_number = request.form.get('case_number')
        if new_case_number != case.case_number:
             if not new_case_number:
                  flash('Case Number cannot be empty.', 'danger')
                  return render_template('edit_case.html', case=case) # Show form again
             existing = Case.query.filter(Case.case_number == new_case_number, Case.id != case_id).first()
             if existing:
                  flash(f'Case Number "{new_case_number}" already exists.', 'danger')
                  return render_template('edit_case.html', case=case) # Show form again
             case.case_number = new_case_number

        # Validate dates and numbers
        try:
             case_date_str = request.form.get('case_date')
             case.case_date = datetime.strptime(case_date_str, '%Y-%m-%d').date() if case_date_str else None
             case.num_sessions = int(request.form.get('num_sessions', 1))
             if case.num_sessions < 0: raise ValueError("Num sessions cannot be negative")
        except (ValueError, TypeError):
             flash('Invalid date or number format provided.', 'danger')
             return render_template('edit_case.html', case=case) # Show form again

        # Get status, default to original if not provided or invalid
        # Note: edit_case.html needs a select dropdown for status for this to work well
        status_str = request.form.get('status', case.status.value)
        try:
            case.status = CaseStatus(status_str.lower())
        except ValueError:
            flash(f'Invalid status "{status_str}" provided, keeping original.', 'warning')
            # Keep original status if new one is invalid

        # Update other fields
        case.next_session_date = request.form.get('next_session_date') or None
        case.session_result = request.form.get('session_result')
        case.case_subject = request.form.get('case_subject')
        case.defendant = request.form.get('defendant')
        case.plaintiff = request.form.get('plaintiff')
        case.prosecution_number = request.form.get('prosecution_number')
        case.police_department = request.form.get('police_department')
        case.police_case_number = request.form.get('police_case_number')
        # case.added_date = datetime.utcnow() # Should not usually update added_date on edit

        try:
            db.session.commit()
            flash(f'Case "{case.case_number}" updated successfully.', 'success')
            return redirect(url_for('list_cases'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating case: {str(e)}', 'danger')

    # GET request
    # Ensure edit_case.html has fields populated with case data
    return render_template('edit_case.html', case=case)


@app.route('/delete_case/<int:case_id>', methods=['POST'])
@login_required
def delete_case(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('list_cases'))

    case = db.session.get(Case, case_id)
    if not case:
        flash('Case not found.', 'danger')
        return redirect(url_for('list_cases'))

    try:
        # Deletion will cascade to DisplayCase due to relationship settings (`cascade="all, delete-orphan"`)
        deleted_order = case.c_order
        case_number = case.case_number # Store for flash message

        db.session.delete(case)

        # Update the order of remaining cases
        # This might be slow with many cases, consider alternatives if performance is an issue
        cases_to_update = Case.query.filter(Case.c_order > deleted_order).order_by(Case.c_order.asc()).all()
        for c in cases_to_update:
            c.c_order -= 1 # Shift order up

        db.session.commit()
        
        # Log activity
        log_activity(
            action='Case Deleted',
            details=f'Deleted case {case_number}',
            court_id=current_user.court_id
        )
        
        flash(f'Case "{case_number}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting case: {str(e)}', 'danger')

    return redirect(url_for('list_cases'))


# --- CHANGE STATUS ROUTE (ENHANCED) ---
@app.route('/change_status/<int:case_id>/<string:status>')
@login_required
def change_status(case_id, status):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('list_cases'))

    case = db.session.get(Case, case_id) # Use db.session.get for PK lookups
    if not case:
        flash('Case not found.', 'danger')
        return redirect(url_for('list_cases')) # Assumes only admins reach here anyway

    try:
        # Check if the provided status string is a valid member of the CaseStatus enum
        old_status = case.status.value if case.status else 'unknown'
        new_status_enum = CaseStatus(status.lower().replace('_', ' ')) # Handle 'in_session' from URL if needed
        case.status = new_status_enum
        db.session.commit()
        
        # Log activity
        log_activity(
            action='Status Changed',
            details=f'Changed status from {old_status} to {new_status_enum.value}',
            case_id=case.id,
            court_id=case.court_id
        )
        
        flash(f'Case "{case.case_number}" status updated to "{new_status_enum.value}".', 'success')
    except ValueError:
        # This handles cases where the string 'status' is not in the Enum definition
        flash(f'Invalid status value provided: "{status}".', 'danger')
    except Exception as e:
        db.session.rollback() # Rollback in case of other commit errors
        flash(f'An error occurred updating status: {str(e)}', 'danger')

    # Redirect back to the cases list or potentially the referrer page
    # Use safe redirect checking
    referrer = request.referrer
    if referrer and urlparse(referrer).path == url_for('list_cases'):
         return redirect(url_for('list_cases'))
    # Add similar checks if you want to redirect back to other specific pages like manage_display
    # elif referrer and urlparse(referrer).path == url_for('manage_display'):
    #      return redirect(url_for('manage_display'))

    return redirect(url_for('list_cases')) # Default fallback redirect


@app.route('/list_users_info')
@login_required
def list_users_info():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    users = User.query.order_by(User.username).all()
    user_list = [{"username": user.username, "name": user.name} for user in users]
    return jsonify(user_list)


# --- Display Management Routes ---
@app.route('/manage_display')
@login_required
def manage_display():
    # Check if user has court assignment or is admin
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))
    
    # If admin without court assignment, show message
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to manage display.', 'info')
        return redirect(url_for('list_users'))

    # Get cases specific to user's court
    all_cases = Case.query.filter_by(court_id=current_user.court_id).order_by(Case.case_number).all()

    # Get displayed cases for user's court
    display_cases = DisplayCase.query.join(Case).filter(
        Case.court_id == current_user.court_id
    ).options(db.joinedload(DisplayCase.case)).order_by(
        DisplayCase.custom_order.asc().nullsfirst(),
        DisplayCase.display_order.asc()
    ).all()

    displayed_case_ids = {dc.case_id for dc in display_cases}

    return render_template('manage_display.html',
                           all_cases=all_cases,
                           display_cases=display_cases,
                           displayed_ids=displayed_case_ids)


@app.route('/add_to_display/<int:case_id>', methods=['POST'])
@login_required
def add_to_display(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('manage_display'))

    # Check if case already in display
    if DisplayCase.query.filter_by(case_id=case_id).first():
        flash(f'Case "{case.case_number}" is already in the display list.', 'warning')
    else:
        # Get the highest display order to append
        highest_order = db.session.query(db.func.max(DisplayCase.display_order)).scalar()
        next_order = 1 if highest_order is None else highest_order + 1

        display_case = DisplayCase(
            case_id=case_id,
            court_id=current_user.court_id,  # Add the court_id
            display_order=next_order,
            custom_order=None
        )
        db.session.add(display_case)
        db.session.commit()
        flash(f'Case "{case.case_number}" added to display.', 'success')

    return redirect(url_for('manage_display'))


@app.route('/remove_from_display/<int:case_id>', methods=['POST'])
@login_required
def remove_from_display(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))

    # Verify case belongs to user's court
    display_case = DisplayCase.query.join(Case).filter(
        DisplayCase.case_id == case_id,
        Case.court_id == current_user.court_id
    ).first()

    display_case = DisplayCase.query.filter_by(case_id=case_id).first()
    if display_case:
        case_number = display_case.case.case_number # Get name for message
        removed_order = display_case.display_order
        db.session.delete(display_case)
        db.session.commit() # Commit deletion first before reordering

        # Update display_order of subsequent items - More robust renumbering
        remaining_display_cases = DisplayCase.query.order_by(DisplayCase.display_order.asc()).all()
        for i, dc in enumerate(remaining_display_cases):
             dc.display_order = i + 1 # Renumber sequentially starting from 1

        db.session.commit() # Commit renumbering
        flash(f'Case "{case_number}" removed from display and list reordered.', 'success')
    else:
        flash('Case not found in display list.', 'warning')

    return redirect(url_for('manage_display'))


@app.route('/update_display_order', methods=['POST'])
@login_required
def update_display_order():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    updated_count = 0
    try:
        # Keep track of orders assigned to prevent duplicates if needed
        assigned_orders = set()
        cases_to_update = []

        for key, value in request.form.items():
            if key.startswith('order_'):
                try:
                    case_id = int(key.split('_')[1])
                    order_val_str = value.strip()
                    # Allow empty string to reset custom order (will use display_order)
                    custom_order = int(order_val_str) if order_val_str else None

                    if custom_order is not None:
                         if custom_order < 1:
                              flash(f'Invalid order value "{order_val_str}" for case ID {case_id}. Must be 1 or greater. Skipping.', 'warning')
                              continue # Skip invalid values
                         # Optional: Check for duplicate custom orders being submitted





                         # if custom_order in assigned_orders:
                         #      flash(f'Order value "{custom_order}" assigned multiple times. Please use unique orders.', 'warning')
                         #      # How to handle duplicates? Skip this one? Invalidate all?
                         #      continue
                         # assigned_orders.add(custom_order)


                    display_case = DisplayCase.query.filter_by(case_id=case_id).first()
                    if display_case and display_case.custom_order != custom_order:
                        display_case.custom_order = custom_order
                        cases_to_update.append(display_case) # Add to list for bulk update/commit
                        updated_count += 1
                except (ValueError, IndexError, TypeError):
                    flash(f'Invalid order input received: {key}={value}', 'warning')

        if updated_count > 0:
             db.session.commit()
             flash(f'Display order updated for {updated_count} case(s).', 'success')
        else:
             flash('No changes detected in display order.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating display order: {str(e)}', 'danger')

    return redirect(url_for('manage_display'))


# This route is likely not needed or needs significant rework if custom_order is used
@app.route('/reorder_display/<int:case_id>/<string:direction>', methods=['POST'])
@login_required
def reorder_display(case_id, direction):
    flash('Button-based reordering is disabled. Please use manual order input.', 'warning')
    return redirect(url_for('manage_display'))


# --- Display Settings Route ---
@app.route('/display_settings', methods=['GET', 'POST'])
@login_required
def display_settings():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    # Define default field names and their AR translations
    default_field_map = {
        "id": "المعرف", # Usually hidden
        "case_number": "رقم الدعوى",
        "case_date": "تاريخ الدعوى",
        "added_date": "تاريخ الإضافة", # Usually hidden
        "c_order": "الترتيب", # Usually hidden
        "next_session_date": "تاريخ الجلسة القادمة",
        "session_result": "نتيجة الجلسة",
        "num_sessions": "رقم الجلسة",
        "case_subject": "موضوع الدعوى",
        "defendant": "المستأنف ضده", # Check terminology
        "plaintiff": "المستأنف", # Check terminology
        "prosecution_number": "الرقم المقابل",
        "police_department": "مركز الشرطة",
        "police_case_number": "رقم الشرطة",
        "status": "الحالة"
    }
    # Get fields directly from the Case model columns
    case_fields = [column.name for column in Case.__table__.columns if column.name != 'id'] # Exclude internal ID

    if request.method == 'POST':
        visible_field_names = request.form.getlist('visible_fields')
        try:
            # Update settings in the database
            for field_name in case_fields:
                setting = DisplaySettings.query.filter_by(field_name=field_name).first()
                # Get AR name from form, use existing or default as fallback
                current_ar_name = setting.field_name_ar if setting else default_field_map.get(field_name, '')
                field_name_ar = request.form.get(f'field_name_ar_{field_name}', current_ar_name)

                if setting:
                    # Update existing setting
                    setting.is_visible = (field_name in visible_field_names)
                    setting.field_name_ar = field_name_ar
                else:
                    # Create new setting if it doesn't exist
                    setting = DisplaySettings(
                        field_name=field_name,
                        field_name_ar=field_name_ar,
                        is_visible=(field_name in visible_field_names)
                    )
                    db.session.add(setting)
            db.session.commit()
            flash('Display settings updated successfully.', 'success')
        except Exception as e:
             db.session.rollback()
             flash(f'Error saving display settings: {str(e)}', 'danger')
        # Redirect back to settings page even after error or success
        return redirect(url_for('display_settings'))

    # GET request: Load current settings
    settings_dict = {setting.field_name: setting for setting in DisplaySettings.query.all()}
    fields_for_template = []
    for field_name in case_fields:
        setting = settings_dict.get(field_name)
        arabic_name = default_field_map.get(field_name, field_name.replace('_', ' ').title())
        if setting and setting.field_name_ar:
            arabic_name = setting.field_name_ar
        fields_for_template.append({
            'name': field_name,
            'is_visible': setting.is_visible if setting else True,
            'field_name_ar': arabic_name
        })

    # Ensure you have a 'settings.html' template
    return render_template('settings.html', fields=fields_for_template)


# --- Public Display Routes ---
@app.route('/general')
def general():
    # Get court_id from logged in user or query parameter
    court_id = current_user.court_id if current_user.is_authenticated else request.args.get('court_id', type=int)

    # If no court_id provided, default to court ID 1 for public access
    if not court_id:
        court_id = 1

    # Get the court details
    court = Court.query.get(court_id)
    if not court:
        # For public access, try to get the first available court
        court = Court.query.filter_by(is_active=True).first()
        if not court:
            return "No active courts available for display", 404
        court_id = court.id

    # Filter display entries by court
    display_entries = DisplayCase.query.join(Case).filter(
        Case.court_id == court_id
    ).options(db.joinedload(DisplayCase.case)).order_by(
        DisplayCase.custom_order.asc().nullsfirst(),
        DisplayCase.display_order.asc()
    ).all()

    # Get only the cases that exist and belong to this court
    cases_to_display = [dc.case for dc in display_entries if dc.case and dc.case.court_id == court_id]

    # Fetch visible fields and their AR names from settings
    settings = DisplaySettings.query.all()
    visible_fields = [s.field_name for s in settings if s.is_visible]
    field_translations = {s.field_name: s.field_name_ar for s in settings if s.field_name_ar}

    # Default fields if none are set as visible
    if not visible_fields:
        visible_fields = ['case_number', 'next_session_date', 'case_subject', 'plaintiff', 'defendant', 'status']
        # Use default AR names for default fields
        default_translations = {
            "case_number": "رقم الدعوى", "next_session_date": "الجلسة القادمة",
            "case_subject": "الموضوع", "plaintiff": "المستأنف",
            "defendant": "المستأنف ضده", "status": "الحالة"
        }
        matching_fields = {field: default_translations.get(field, field.replace('_', ' ').title()) for field in visible_fields}
    else:
        # Use translations from DB, fallback to title case
         matching_fields = {field: field_translations.get(field, field.replace('_', ' ').title()) for field in visible_fields}

    # Fetch cases based on DisplayCase entries, ordered correctly
    # Use joinedload to prevent N+1 query problem when accessing case.status, case.case_number etc. in template
    display_entries = DisplayCase.query.options(db.joinedload(DisplayCase.case)).order_by(
         DisplayCase.custom_order.asc().nullsfirst(), # Nulls first means manually ordered appear first in their order
         DisplayCase.display_order.asc() # Then sort by original add order
     ).all()

    # Filter out entries where the related case might have been deleted somehow (shouldn't happen with cascade)
    cases_to_display = [dc.case for dc in display_entries if dc.case]

    return render_template('general.html',
                           court=court,
                           cases=cases_to_display,
                           visible_fields=visible_fields,
                           matching_fields=matching_fields)


# --- User Management Routes (Admin Only) ---
@app.route('/users')
@login_required
def list_users():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    users = User.query.order_by(User.name).all()
    return render_template('users.html', users=users) # Ensure you have users.html template

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    # Redirect to admin add user route
    return redirect(url_for('admin_add_user'))


@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('list_users'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('list_users'))
    
    courts = Court.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password') # Optional: only set if provided

        # Validate username/email uniqueness if changed
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

        # Update password only if a new one is entered
        if password:
            user.password = generate_password_hash(password)

        # Update court assignment
        new_court_id = request.form.get('court_id')
        if new_court_id:
            user.court_id = int(new_court_id)
        elif not request.form.get('is_admin'):  # Non-admin users must have court assignment
            flash('Court assignment is required for non-admin users.', 'warning')
            return render_template('edit_user.html', user=user, courts=courts)

        user.name = request.form.get('name', user.name)
        user.tel = request.form.get('tel', user.tel)
        # Prevent admin from accidentally removing their own admin rights if they are the only admin?
        is_potentially_removing_last_admin = (
             user.is_admin and # Was admin before
             request.form.get('is_admin') != 'on' and # Is being changed to non-admin
             User.query.filter_by(is_admin=True).count() == 1 and # Is the only admin
             user.id == current_user.id # Is the current logged-in user (extra safety)
        )
        if is_potentially_removing_last_admin:
             flash('Cannot remove admin rights from the last administrator.', 'danger')
             return render_template('edit_user.html', user=user)

        user.is_admin = request.form.get('is_admin') == 'on'

        try:
            db.session.commit()
            flash(f'User "{user.username}" updated successfully.', 'success')
            return redirect(url_for('list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')

    # GET request
    return render_template('edit_user.html', user=user, courts=courts)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user = db.session.get(User, user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('list_users'))

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
    # Add check: prevent deleting the last admin user?
    elif user.is_admin and User.query.filter_by(is_admin=True).count() == 1:
         flash('Cannot delete the last administrator account.', 'danger')
    else:
        try:
            username = user.username # Get name for message
            db.session.delete(user)
            db.session.commit()
            flash(f'User "{username}" deleted successfully.', 'success')
        except Exception as e:
             db.session.rollback()
             flash(f'Error deleting user: {str(e)}', 'danger')

    return redirect(url_for('list_users'))


# --- Court Management Routes ---
@app.route('/courts')
@login_required
def list_courts():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    courts = Court.query.all()
    return render_template('courts.html', courts=courts)

@app.route('/add_court', methods=['GET', 'POST'])
@login_required
def add_court():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Court name is required.', 'danger')
            return render_template('add_court.html')

        if Court.query.filter_by(name=name).first():
            flash('Court name already exists.', 'danger')
            return render_template('add_court.html')

        court = Court(name=name, description=description, is_active=is_active)
        db.session.add(court)
        db.session.commit()
        flash(f'Court "{name}" added successfully.', 'success')
        return redirect(url_for('list_courts'))

    return render_template('add_court.html')

@app.route('/edit_court/<int:court_id>', methods=['GET', 'POST'])
@login_required
def edit_court(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('list_courts'))

    court = Court.query.get_or_404(court_id)

    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Court name is required.', 'danger')
            return render_template('edit_court.html', court=court)

        existing = Court.query.filter(Court.name == name, Court.id != court_id).first()
        if existing:
            flash('Court name already exists.', 'danger')
            return render_template('edit_court.html', court=court)

        court.name = name
        court.description = request.form.get('description')
        court.is_active = request.form.get('is_active') == 'on'
        db.session.commit()
        flash(f'Court "{name}" updated successfully.', 'success')
        return redirect(url_for('list_courts'))

    return render_template('edit_court.html', court=court)

@app.route('/view_court_details/<int:court_id>')
@login_required
def view_court_details(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    court = Court.query.get_or_404(court_id)
    
    # Get court statistics
    total_cases = len(court.cases)
    active_cases = [case for case in court.cases if case.status == CaseStatus.active]
    inactive_cases = [case for case in court.cases if case.status == CaseStatus.inactive]
    finished_cases = [case for case in court.cases if case.status == CaseStatus.finished]
    
    # Get recent cases (last 10)
    recent_cases = Case.query.filter_by(court_id=court_id).order_by(Case.added_date.desc()).limit(10).all()
    
    # Get display cases
    display_cases = DisplayCase.query.join(Case).filter(Case.court_id == court_id).all()
    
    return render_template('court_details.html', 
                         court=court,
                         total_cases=total_cases,
                         active_cases=active_cases,
                         inactive_cases=inactive_cases,
                         finished_cases=finished_cases,
                         recent_cases=recent_cases,
                         display_cases=display_cases)

@app.route('/court_cases/<int:court_id>')
@login_required
def court_cases(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    court = Court.query.get_or_404(court_id)
    
    # Get filter parameters
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    
    # Base query
    query = Case.query.filter_by(court_id=court_id)
    
    # Apply filters
    if status_filter and status_filter != 'all':
        try:
            status_enum = CaseStatus(status_filter)
            query = query.filter(Case.status == status_enum)
        except ValueError:
            pass
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(Case.case_date == filter_date)
        except ValueError:
            pass
    
    cases = query.order_by(Case.case_date.desc(), Case.c_order.asc()).all()
    
    return render_template('court_cases.html', 
                         court=court, 
                         cases=cases,
                         status_options=list(CaseStatus),
                         current_status=status_filter,
                         current_date=date_filter)

@app.route('/impersonate_user/<int:user_id>')
@login_required
def impersonate_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    user_to_impersonate = db.session.get(User, user_id)
    if not user_to_impersonate:
        flash('User not found.', 'danger')
        return redirect(url_for('list_users'))
    
    # Store the original admin user ID in session
    session['original_admin_id'] = current_user.id
    session['impersonating'] = True
    
    # Login as the target user
    logout_user()
    login_user(user_to_impersonate)
    
    flash(f'You are now impersonating {user_to_impersonate.name} ({user_to_impersonate.username})', 'info')
    return redirect(url_for('index'))

@app.route('/stop_impersonation')
@login_required
def stop_impersonation():
    if not session.get('impersonating'):
        flash('You are not currently impersonating another user.', 'warning')
        return redirect(url_for('index'))
    
    # Get the original admin user
    original_admin_id = session.get('original_admin_id')
    if not original_admin_id:
        flash('Cannot restore original session.', 'danger')
        return redirect(url_for('login'))
    
    original_admin = db.session.get(User, original_admin_id)
    if not original_admin:
        flash('Original admin user not found.', 'danger')
        return redirect(url_for('login'))
    
    # Clear impersonation session data
    session.pop('original_admin_id', None)
    session.pop('impersonating', None)
    
    # Login back as admin
    logout_user()
    login_user(original_admin)
    
    flash('Impersonation ended. You are back to your admin account.', 'success')
    return redirect(url_for('list_courts'))

# --- Statistics Route ---
@app.route('/statistics')
@login_required
def statistics():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    court_id = request.args.get('court_id')
    
    # Base queries
    case_query = Case.query
    activity_query = ActivityLog.query
    
    # Apply date filters
    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            case_query = case_query.filter(Case.case_date >= start_date_obj)
            activity_query = activity_query.filter(ActivityLog.created_at >= start_date_obj)
        except ValueError:
            flash('Invalid start date format', 'warning')
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            case_query = case_query.filter(Case.case_date <= end_date_obj)
            activity_query = activity_query.filter(ActivityLog.created_at <= end_date_obj)
        except ValueError:
            flash('Invalid end date format', 'warning')
    
    if court_id:
        case_query = case_query.filter(Case.court_id == court_id)
        activity_query = activity_query.filter(ActivityLog.court_id == court_id)
    
    # Get all cases for summary
    all_cases = case_query.all()
    
    # Calculate summary statistics
    today = datetime.now().date()
    first_day_of_month = today.replace(day=1)
    new_cases_this_month = Case.query.filter(
        Case.added_date >= first_day_of_month,
        Case.added_date <= datetime.now()
    ).count()
    
    summary = {
        'total_cases': len(all_cases),
        'active_cases': len([c for c in all_cases if c.status == CaseStatus.in_session]),
        'finished_cases': len([c for c in all_cases if c.status == CaseStatus.finished]),
        'postponed_cases': len([c for c in all_cases if c.status == CaseStatus.postponed]),
        'inactive_cases': len([c for c in all_cases if c.status == CaseStatus.inactive]),
        'new_cases_this_month': new_cases_this_month,
        'total_courts': Court.query.filter_by(is_active=True).count(),
        'total_users': User.query.count()
    }
    
    # Status distribution
    status_distribution = [
        summary['active_cases'],
        summary['inactive_cases'],
        summary['postponed_cases'],
        summary['finished_cases']
    ]
    
    # Monthly trend data (last 12 months)
    monthly_data = []
    monthly_labels = []
    monthly_new_cases = []
    monthly_finished_cases = []
    
    for i in range(11, -1, -1):
        month_date = today - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year+1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month+1, day=1) - timedelta(days=1)
        
        new_count = Case.query.filter(
            Case.added_date >= month_start,
            Case.added_date <= month_end
        ).count()
        
        finished_count = ActivityLog.query.filter(
            ActivityLog.action == 'Status Changed',
            ActivityLog.details.like('%finished%'),
            ActivityLog.created_at >= month_start,
            ActivityLog.created_at <= month_end
        ).count()
        
        monthly_labels.append(month_date.strftime('%Y-%m'))
        monthly_new_cases.append(new_count)
        monthly_finished_cases.append(finished_count)
    
    # Court statistics
    courts = Court.query.filter_by(is_active=True).all()
    court_statistics = []
    
    for court in courts:
        court_cases = [c for c in all_cases if c.court_id == court.id]
        total = len(court_cases)
        active = len([c for c in court_cases if c.status == CaseStatus.in_session])
        finished = len([c for c in court_cases if c.status == CaseStatus.finished])
        postponed = len([c for c in court_cases if c.status == CaseStatus.postponed])
        
        completion_rate = round((finished / total * 100), 1) if total > 0 else 0
        
        # Calculate average case duration
        finished_cases = [c for c in court_cases if c.status == CaseStatus.finished and c.case_date]
        avg_duration = 0
        if finished_cases:
            total_days = sum([(datetime.now().date() - c.case_date).days for c in finished_cases])
            avg_duration = round(total_days / len(finished_cases))
        
        court_statistics.append({
            'court_name': court.name,
            'total_cases': total,
            'active_cases': active,
            'finished_cases': finished,
            'postponed_cases': postponed,
            'completion_rate': completion_rate,
            'avg_duration': avg_duration
        })
    
    # User statistics
    users = User.query.all()
    user_statistics = []
    
    for user in users:
        user_cases = Case.query.filter_by(user_id=user.id)
        if start_date and end_date:
            user_cases = user_cases.filter(
                Case.added_date >= datetime.strptime(start_date, '%Y-%m-%d'),
                Case.added_date <= datetime.strptime(end_date, '%Y-%m-%d')
            )
        
        last_activity = ActivityLog.query.filter_by(user_id=user.id).order_by(
            ActivityLog.created_at.desc()
        ).first()
        
        user_statistics.append({
            'username': user.username,
            'cases_added': user_cases.count(),
            'last_activity': last_activity.created_at if last_activity else None
        })
    
    # Recent activities (last 10)
    recent_activities = ActivityLog.query.order_by(
        ActivityLog.created_at.desc()
    ).limit(10).all()
    
    # Status changes timeline (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    status_changes = ActivityLog.query.filter(
        ActivityLog.action == 'Status Changed',
        ActivityLog.created_at >= thirty_days_ago
    ).all()
    
    # Group by day
    status_changes_by_day = {}
    for activity in status_changes:
        day = activity.created_at.strftime('%Y-%m-%d')
        status_changes_by_day[day] = status_changes_by_day.get(day, 0) + 1
    
    status_changes_labels = list(status_changes_by_day.keys())
    status_changes_data = list(status_changes_by_day.values())
    
    return render_template('statistics.html',
                         summary=summary,
                         status_distribution=status_distribution,
                         monthly_labels=monthly_labels,
                         monthly_new_cases=monthly_new_cases,
                         monthly_finished_cases=monthly_finished_cases,
                         court_statistics=court_statistics,
                         user_statistics=user_statistics,
                         recent_activities=recent_activities,
                         status_changes_labels=status_changes_labels,
                         status_changes_data=status_changes_data,
                         courts=courts,
                         start_date=start_date,
                         end_date=end_date,
                         court_id=court_id)

@app.route('/export_report/<format>')
@login_required
def export_report(format):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    
    if format == 'excel':
        return export_excel_report()
    elif format == 'pdf':
        return export_pdf_report()
    else:
        flash('Invalid export format', 'danger')
        return redirect(url_for('statistics'))

def export_excel_report():
    try:
        import pandas as pd
        from io import BytesIO
        
        # Create workbook
        output = BytesIO()
        
        # Get data
        cases = Case.query.all()
        courts = Court.query.all()
        users = User.query.all()
        activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(1000).all()
        
        # Create DataFrames
        cases_data = []
        for case in cases:
            cases_data.append({
                'رقم القضية': case.case_number,
                'تاريخ القضية': case.case_date.strftime('%Y-%m-%d') if case.case_date else '',
                'الحالة': case.status.value if case.status else '',
                'الموضوع': case.case_subject or '',
                'المستأنف': case.plaintiff or '',
                'المستأنف ضده': case.defendant or '',
                'المحكمة': case.court.name if case.court else '',
                'المستخدم': case.user.username if case.user else ''
            })
        
        activities_data = []
        for activity in activities:
            activities_data.append({
                'التاريخ': activity.created_at.strftime('%Y-%m-%d %H:%M'),
                'المستخدم': activity.user.username if activity.user else '',
                'النشاط': activity.action,
                'التفاصيل': activity.details or '',
                'المحكمة': activity.court.name if activity.court else ''
            })
        
        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(cases_data).to_excel(writer, sheet_name='القضايا', index=False)
            pd.DataFrame(activities_data).to_excel(writer, sheet_name='سجل الأنشطة', index=False)
        
        output.seek(0)
        
        return send_file(
            BytesIO(output.read()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'تقرير_شامل_{datetime.now().strftime("%Y-%m-%d")}.xlsx'
        )
    except ImportError:
        flash('Excel export requires pandas library', 'danger')
        return redirect(url_for('statistics'))
    except Exception as e:
        flash(f'Error exporting Excel: {str(e)}', 'danger')
        return redirect(url_for('statistics'))

def export_pdf_report():
    flash('PDF export feature coming soon', 'info')
    return redirect(url_for('statistics'))

# --- Control Panel Route ---
@app.route('/control')
@login_required
def control():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('index'))
    # Fetch data needed for control panel template
    users = User.query.all() # Maybe only fetch counts? Depends on template needs
    cases = Case.query.all()
    return render_template('control.html', users=users, cases=cases)


# --- Development/Utility Route ---
# Renamed for safety - requires explicit confirmation via form POST
@app.route('/drop_all_tables_confirm')
@login_required
def drop_all_tables_confirm_page():
     """Show a confirmation page before dropping tables."""
     if not current_user.is_admin:
          flash('Access denied.', 'danger')
          return redirect(url_for('index'))
     # You MUST create a 'confirm_drop.html' template for this
     # This template should contain a form that POSTs to /drop_all_tables_execute
     # It should have strong warnings about data loss and a text input for confirmation.
     # Example confirm_drop.html content:
     # <h2>Confirm Database Reset</h2>
     # <p class="text-danger"><strong>Warning:</strong> This will delete ALL data (users, cases, settings) and cannot be undone.</p>
     # <form method="POST" action="{{ url_for('drop_all_tables_execute') }}">
     #    <label for="confirmation_text">Type "CONFIRM DELETE ALL DATA" to proceed:</label>
     #    <input type="text" id="confirmation_text" name="confirmation_text" required>
     #    <button type="submit" class="btn btn-danger">Reset Database</button>
     # </form>
     return render_template('confirm_drop.html') # Make sure this template exists!


@app.route('/drop_all_tables_execute', methods=['POST'])
@login_required
def drop_all_tables_execute():
    """Actually drops and recreates tables after confirmation."""
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    # Add an extra check, e.g., require admin to type "CONFIRM DELETE" in a form field
    confirmation_text = request.form.get('confirmation_text')
    if confirmation_text != "CONFIRM DELETE ALL DATA":
         flash('Incorrect confirmation text. Database reset aborted.', 'danger')
         return redirect(url_for('drop_all_tables_confirm_page'))

    print("!!! EXECUTING DROP ALL TABLES !!!")
    try:
        # Drop and recreate all tables defined in the models
        # Ensure Flask-Migrate is not interfering if using migrations heavily
        db.drop_all()
        db.create_all()
        flash('All database tables dropped and recreated.', 'warning')

        # Re-create default admin and settings
        create_defaults() # Helper function defined below
        flash('Default admin user and display settings initialized.', 'info')

    except Exception as e:
        flash(f'Error during database reset: {str(e)}', 'danger')
        # Attempt to rollback if create_all failed partially? Difficult state.
        db.session.rollback()

    return redirect(url_for('index'))

# --- Helper function for defaults ---
def create_defaults():
     """Creates default admin user and display settings if they don't exist."""
     # Create default admin if no users exist
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
         print("Default admin user created:")
         print("Username: admin")
         print("Password: admin123")

     # Initialize default display settings if none exist
     if not DisplaySettings.query.first():
         default_field_map = {
             "id": "المعرف", "case_number": "رقم الدعوى", "case_date": "تاريخ الدعوى",
             "added_date": "تاريخ الإضافة", "c_order": "الترتيب",
             "next_session_date": "تاريخ الجلسة القادمة", "session_result": "نتيجة الجلسة",
             "num_sessions": "رقم الجلسة", "case_subject": "موضوع الدعوى",
             "defendant": "المستأنف ضده", "plaintiff": "المستأنف",
             "prosecution_number": "الرقم المقابل", "police_department": "مركز الشرطة",
             "police_case_number": "رقم الشرطة", "status": "الحالة"
         }
         # Default visible fields
         default_visible = ['case_number', 'next_session_date', 'case_subject',
                            'plaintiff', 'defendant', 'status']
         case_fields = [column.name for column in Case.__table__.columns if column.name != 'id'] # Exclude id

         for field_name in case_fields:
             # Check if setting already exists (paranoid check, query above should suffice)
             if not DisplaySettings.query.filter_by(field_name=field_name).first():
                 setting = DisplaySettings(
                     field_name=field_name,
                     field_name_ar=default_field_map.get(field_name, field_name.replace('_', ' ').title()),
                     is_visible=(field_name in default_visible)
                 )
                 db.session.add(setting)
         print("Default display settings created.")

     try:
          # Only commit if changes were potentially made
          if db.session.new or db.session.dirty:
               db.session.commit()
     except Exception as e:
          db.session.rollback()
          print(f"Error committing defaults: {e}")


# Add this route to your app.py

@app.route('/general_control')
@login_required
def general_control():
    # Check if user has court assignment or is admin
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('index'))
    
    # If admin without court assignment, show message
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to control display.', 'info')
        return redirect(url_for('list_users'))

    try:
        # Filter display entries by user's court
        display_entries = DisplayCase.query.join(Case).filter(
            Case.court_id == current_user.court_id
        ).options(db.joinedload(DisplayCase.case)).order_by(
            DisplayCase.custom_order.asc().nullslast(),
            DisplayCase.display_order.asc()
        ).all()
        cases_to_display = [dc for dc in display_entries if dc.case]

        # --- ADDED: Pass the list of enum members to the template ---
        status_options = list(CaseStatus)
        # ----------------------------------------------------------

        return render_template(
            'general_control.html',
            display_entries=cases_to_display,
            status_options=status_options # Pass the options here
        )

    except Exception as e:
         print(f"Error fetching data for /general_control: {e}")
         import traceback
         print(traceback.format_exc())
         flash("An error occurred while loading the case reorder page.", "danger")
         return redirect(url_for('index'))

# Add this route to your app.py

@app.route('/update_display_order_ajax', methods=['POST'])
@login_required
def update_display_order_ajax():
    """
    Handles AJAX request from the drag-and-drop interface
    to update the custom_order of displayed cases.
    Publishes an SSE event on successful update.
    """
    # 1. Check Permissions
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    # 2. Check Request Format
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request: Content-Type must be application/json'}), 400

    # 3. Get Data from Request
    data = request.get_json()
    ordered_case_ids_str = data.get('order') # Expecting a list of strings/numbers representing case_ids

    # 4. Validate Data
    if not isinstance(ordered_case_ids_str, list):
        return jsonify({'success': False, 'message': 'Invalid data format: "order" array not found or not a list.'}), 400

    # Convert IDs to integers, handling potential errors
    ordered_case_ids = []
    for idx, case_id_str in enumerate(ordered_case_ids_str):
        try:
            ordered_case_ids.append(int(case_id_str))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': f'Invalid case ID format found at position {idx}: {case_id_str}. Expected integers.'}), 400

    if not ordered_case_ids:
        # Handle empty list if needed, maybe return success as no change needed?
        return jsonify({'success': True, 'message': 'Received empty order list. No changes made.'})

    # 5. Update Database
    try:
        # Fetch all relevant DisplayCase objects efficiently using IN clause
        display_cases_dict = {dc.case_id: dc for dc in DisplayCase.query.filter(DisplayCase.case_id.in_(ordered_case_ids)).all()}

        updated_count = 0
        # Iterate through the desired order received from the frontend
        for index, case_id in enumerate(ordered_case_ids):
            new_order = index + 1 # Calculate 1-based order

            display_case = display_cases_dict.get(case_id)
            if display_case:
                # Update custom_order only if it has actually changed
                if display_case.custom_order != new_order:
                    display_case.custom_order = new_order
                    updated_count += 1
            else:
                # Log warning if a case ID from frontend isn't in the display list
                # This could happen if a case was removed from display in another browser tab
                print(f"Warning: Case ID {case_id} received from frontend but not found in DisplayCase table during reorder.")

        # Only commit if changes were actually made
        if updated_count > 0:
            db.session.commit()
            message = f'Successfully updated order for {updated_count} case(s).'
            print(message) # Log success on server

            # 6. Publish SSE Event on successful commit
            try:
                 sse.publish({"update_type": "order", "message": "Display order changed"}, type='display_update')
                 print("SSE event 'display_update' published for order change.")
            except Exception as sse_error:
                 # Log error if SSE publish fails but don't fail the whole request
                 print(f"Warning: Failed to publish SSE event after order update: {sse_error}")

            return jsonify({'success': True, 'message': message})
        else:
            # No database changes were needed
            return jsonify({'success': True, 'message': 'No order changes were necessary.'})

    except Exception as e:
        db.session.rollback() # Rollback transaction on any error
        # Log the detailed error on the server
        print(f"Error updating display order via AJAX: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # Return a generic error message to the client
        return jsonify({'success': False, 'message': 'A database error occurred while saving the new order.'}), 500



# Add this route to app.py
# Make sure to import request, flash, redirect, url_for, jsonify if not already done
# Also ensure Case, db models are imported

@app.route('/delete_selected_cases', methods=['POST'])
@login_required
def delete_selected_cases():
    """Handles deleting multiple cases selected via checkboxes."""
    case_ids_to_delete_str = request.form.getlist('selected_case_ids')

    if not case_ids_to_delete_str:
        flash('No cases were selected for deletion.', 'warning')
        return redirect(url_for('list_cases'))

    # Convert IDs to integers for database query
    case_ids_to_delete = []
    invalid_ids = []
    for id_str in case_ids_to_delete_str:
        try:
            case_ids_to_delete.append(int(id_str))
        except ValueError:
            invalid_ids.append(id_str)

    if invalid_ids:
        flash(f"Invalid case IDs received: {', '.join(invalid_ids)}. Deletion aborted.", 'danger')
        return redirect(url_for('list_cases'))

    deleted_count = 0
    errors = []

    try:
        # Fetch cases that belong to the current user or if user is admin
        query = Case.query.filter(Case.id.in_(case_ids_to_delete))
        if not current_user.is_admin:
            query = query.filter(Case.user_id == current_user.id)

        cases_to_delete = query.all()

        if not cases_to_delete:
            flash('No cases found or you do not have permission to delete them.', 'warning')
            return redirect(url_for('list_cases'))

        for case in cases_to_delete:
            db.session.delete(case)
            deleted_count += 1

        db.session.commit()
        flash(f'Successfully deleted {deleted_count} case(s).', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"Error during bulk case deletion: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash(f'An error occurred during deletion: {str(e)}', 'danger')

    return redirect(url_for('list_cases'))

    # Get the list of case IDs from the form checkboxes
    case_ids_to_delete_str = request.form.getlist('selected_case_ids')

    if not case_ids_to_delete_str:
        flash('No cases were selected for deletion.', 'warning')
        return redirect(url_for('list_cases'))

    # Convert IDs to integers for database query
    case_ids_to_delete = []
    invalid_ids = []
    for id_str in case_ids_to_delete_str:
        try:
            case_ids_to_delete.append(int(id_str))
        except ValueError:
            invalid_ids.append(id_str)

    if invalid_ids:
        flash(f"Invalid case IDs received: {', '.join(invalid_ids)}. Deletion aborted.", 'danger')
        return redirect(url_for('list_cases'))

    deleted_count = 0
    errors = []

    try:
        # Fetch cases to be deleted (safer than bulk delete command with cascades)
        cases_to_delete = Case.query.filter(Case.id.in_(case_ids_to_delete)).all()

        if not cases_to_delete:
             flash('None of the selected cases were found in the database.', 'warning')
             return redirect(url_for('list_cases'))

        for case in cases_to_delete:
            # Deletion should cascade to DisplayCase due to relationship settings
            db.session.delete(case)
            deleted_count += 1

        # Commit all deletions at once
        db.session.commit()

        flash(f'Successfully deleted {deleted_count} case(s).', 'success')

        # IMPORTANT: Skipping c_order re-numbering for bulk delete due to complexity.
        # If sequential c_order is critical, this needs more complex logic.

    except Exception as e:
        db.session.rollback()
        print(f"Error during bulk case deletion: {str(e)}")
        import traceback
        print(traceback.format_exc())
        flash(f'An error occurred during deletion: {str(e)}', 'danger')

    return redirect(url_for('list_cases'))

# === Application Runner ===
if __name__ == '__main__':
    with app.app_context():
        # Optional: Create tables if they don't exist on startup
        # db.create_all() # Usually handled by migrations (Flask-Migrate)

        # Create default admin/settings ONLY if the database is truly empty
        # This check might need adjustment depending on how migrations are handled
        # For simplicity, let's check for the User table specifically
        try:
             from sqlalchemy import inspect
             inspector = inspect(db.engine)
             if not inspector.has_table(User.__tablename__):
                  print("User table not found, attempting to create tables and defaults.")
                  db.create_all() # Create all tables if user table is missing
                  create_defaults()
             else:
                  # Check if defaults *should* be created even if tables exist (e.g., first run)
                  create_defaults() # Call it anyway, it has internal checks
        except Exception as e:
             print(f"Error during initial setup check: {e}")
             print("Please ensure database is initialized correctly (e.g., using 'flask db upgrade')")

    # Run the Flask development server
    # Use host='0.0.0.0' to make it accessible on your network (use with caution)
    # Set debug=False for production!
    #app.run(debug=True, host='0.0.0.0', port=5000)

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)