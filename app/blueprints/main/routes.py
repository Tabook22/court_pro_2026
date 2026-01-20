import os
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from flask import render_template, redirect, url_for, flash, request, jsonify, send_from_directory, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models.models import User, Case, CaseStatus, DisplayCase, DisplaySettings, ActivityLog, Court
from extensions import db
from app.utils.excel_processor import ExcelProcessor
from app.utils.json_importer import JsonToDatabase
from . import main_bp

@main_bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    if current_user.is_admin:
        users = User.query.all()
        cases = Case.query.all()
        return render_template('control.html', users=users, cases=cases)
    else:
        if not current_user.court_id:
            flash('No court assigned to your account.', 'danger')
            return redirect(url_for('auth.login'))

        court_cases = Case.query.filter_by(court_id=current_user.court_id).order_by(Case.added_date.desc()).all()
        active_cases = [case for case in court_cases if case.status == CaseStatus.active]
        display_cases = DisplayCase.query.join(Case).filter(Case.court_id == current_user.court_id).all()
        latest_cases = court_cases[:10]

        return render_template('user_dashboard.html', 
                             cases=court_cases,
                             active_cases=active_cases,
                             display_cases=display_cases,
                             latest_cases=latest_cases,
                             court=current_user.court)

@main_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    if 'excelFile' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400

    file = request.files['excelFile']

    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if file and file.filename.lower().endswith(('.xls', '.xlsx')):
        current_date = datetime.now()
        year_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_date.year))
        month_folder = os.path.join(year_folder, current_date.strftime('%m-%B'))
        date_folder = os.path.join(month_folder, current_date.strftime('%d'))

        os.makedirs(date_folder, exist_ok=True)

        timestamp = int(time.time())
        _, file_extension = os.path.splitext(file.filename)
        safe_base = secure_filename(os.path.splitext(file.filename)[0])
        if not safe_base:
             safe_base = "uploaded_file"
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

@main_bp.route('/list_files')
@login_required
def list_files():
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    def is_file_accessible(filename):
        if current_user.is_admin:
            return True
        court_prefix = f"court_{current_user.court_id}_"
        return filename.startswith(court_prefix)

    files_data_sorted = defaultdict(list)
    upload_root = current_app.config['UPLOAD_FOLDER']

    if not os.path.exists(upload_root):
        return render_template('list_files.html', files_by_year_month_sorted={})

    try:
        years = sorted(
            [d for d in os.listdir(upload_root) if os.path.isdir(os.path.join(upload_root, d)) and d.isdigit()],
            key=int,
            reverse=True
        )
    except OSError as e:
        flash(f"Error accessing upload directory: {e}", 'danger')
        return render_template('list_files.html', files_by_year_month_sorted={})

    for year in years:
        year_path = os.path.join(upload_root, year)
        temp_month_files = defaultdict(list)

        try:
            month_dirs = [d for d in os.listdir(year_path) if os.path.isdir(os.path.join(year_path, d))]
        except OSError:
            continue

        for month in month_dirs:
            month_path = os.path.join(year_path, month)
            try:
                days = sorted(
                    [d for d in os.listdir(month_path) if os.path.isdir(os.path.join(month_path, d)) and d.isdigit()],
                    key=int,
                    reverse=True
                )
            except OSError:
                continue

            for day in days:
                day_path = os.path.join(month_path, day)
                try:
                    files = sorted([f for f in os.listdir(day_path) 
                                  if os.path.isfile(os.path.join(day_path, f)) and is_file_accessible(f)])
                    if files:
                        temp_month_files[month].extend([os.path.join(day, file) for file in files])
                    else:
                        try:
                            os.rmdir(day_path)
                        except OSError:
                            pass
                except Exception:
                    pass

            try:
                if os.path.exists(month_path) and not os.listdir(month_path):
                    os.rmdir(month_path)
            except OSError:
                 pass

        if temp_month_files:
            def sort_key_month(month_item_tuple):
                month_str = month_item_tuple[0]
                if '-' in month_str and month_str.split('-')[0].isdigit():
                    return int(month_str.split('-')[0])
                else:
                    return 0

            sorted_month_items_list = sorted(
                temp_month_files.items(),
                key=sort_key_month,
                reverse=True
            )
            files_data_sorted[year] = sorted_month_items_list

        try:
             if os.path.exists(year_path) and not os.listdir(year_path):
                 os.rmdir(year_path)
        except OSError:
             pass

    return render_template('list_files.html', files_by_year_month_sorted=files_data_sorted)

@main_bp.route('/delete_file', methods=['POST'])
@login_required
def delete_file():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403

    year = request.form.get('year')
    month = request.form.get('month')
    file_rel_path = request.form.get('file')

    if not all([year, month, file_rel_path]):
        return jsonify({'success': False, 'message': 'Invalid file information provided'}), 400

    year = secure_filename(year)
    month = secure_filename(month)
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts):
         return jsonify({'success': False, 'message': 'Invalid file path component detected'}), 400
    safe_rel_path = os.path.join(*safe_parts)

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], year, month, safe_rel_path)
    day_folder = os.path.dirname(file_path)
    month_folder = os.path.dirname(day_folder)
    year_folder = os.path.dirname(month_folder)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            os.remove(file_path)
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
        return jsonify({'success': False, 'message': 'File not found'}), 404

@main_bp.route('/view_file/<year>/<month>/<path:file_rel_path>')
@login_required
def view_file(year, month, file_rel_path):
    year = secure_filename(year)
    month = secure_filename(month)
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts):
         return "Invalid path component", 400

    directory = os.path.join(current_app.config['UPLOAD_FOLDER'], year, month, *safe_parts[:-1])
    filename = safe_parts[-1]

    if not os.path.abspath(directory).startswith(os.path.abspath(current_app.config['UPLOAD_FOLDER'])):
         return "Access denied", 403

    try:
        return send_from_directory(directory, filename, as_attachment=False)
    except FileNotFoundError:
        return "File not found", 404
    except Exception as e:
         print(f"Error serving file {directory}/{filename}: {e}")
         return "Error serving file", 500

@main_bp.route('/process_excel', methods=['POST'])
@login_required
def process_excel():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    year = request.form.get('year')
    month = request.form.get('month')
    file_rel_path = request.form.get('file')

    if not all([year, month, file_rel_path]):
        return jsonify({'success': False, 'message': 'Invalid file information provided'}), 400

    year = secure_filename(year)
    month = secure_filename(month)
    parts = file_rel_path.replace('\\', '/').split('/')
    safe_parts = [secure_filename(part) for part in parts]
    if any('..' in part or part.startswith('/') for part in safe_parts):
         return jsonify({'success': False, 'message': 'Invalid file path component detected'}), 400
    safe_rel_path = os.path.join(*safe_parts)

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], year, month, safe_rel_path)

    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found'}), 404

    processor = ExcelProcessor(json_storage_path=current_app.config['JSON_STORAGE'])
    result = processor.process_excel_file(file_path)

    if result.get('success'):
        return jsonify({
            'success': True,
            'message': result.get('message', 'File processed successfully.'),
            'schema': result.get('schema'),
            'json_filename': result.get('json_filename')
        })
    else:
        return jsonify({
            'success': False,
            'message': result.get('message', 'Error processing file.'),
            'error': result.get('error')
        }), 500

@main_bp.route('/processed_json/<filename>')
@login_required
def serve_processed_json(filename):
    filename = secure_filename(filename)
    if '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400
    try:
        return send_from_directory(current_app.config['JSON_STORAGE'], filename)
    except FileNotFoundError:
        return "JSON file not found", 404

@main_bp.route('/import_to_database', methods=['POST'])
@login_required
def import_to_database():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    json_filename = request.form.get('json_filename')
    if not json_filename:
        return jsonify({'success': False, 'message': 'No JSON file specified'}), 400

    json_filename = secure_filename(json_filename)
    if '..' in json_filename or json_filename.startswith('/'):
        return jsonify({'success': False, 'message': 'Invalid JSON filename'}), 400

    try:
        importer = JsonToDatabase(db.session, current_user.court_id, current_app.config['JSON_STORAGE'])
        case_data_list = importer.process_json_file(json_filename)

        if case_data_list is None:
            return jsonify({'success': False, 'message': f'Failed to read or parse JSON file: {json_filename}'}), 500

        result = importer.import_data(case_data_list, current_user.id)

        message = f"Import completed. Cases added: {result.get('cases_added', 0)}."
        skipped_count = len(result.get('skipped', []))
        error_count = len(result.get('errors', []))

        if skipped_count > 0:
            message += f" Records skipped: {skipped_count} (Duplicates or data issues)."
        if error_count > 0:
             message += f" Errors encountered: {error_count}."

        return jsonify({
            'success': result.get('success', False),
            'message': message,
            'cases_added': result.get('cases_added', 0),
            'skipped_count': skipped_count,
            'error_count': error_count,
        })

    except Exception as e:
        print(f"Exception during import route execution for {json_filename}: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'An unexpected server error occurred during the import process.'
        }), 500

@main_bp.route('/courts')
@login_required
def list_courts():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    courts = Court.query.all()
    return render_template('courts.html', courts=courts)

@main_bp.route('/add_court', methods=['GET', 'POST'])
@login_required
def add_court():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

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
        return redirect(url_for('main.list_courts'))

    return render_template('add_court.html')

@main_bp.route('/edit_court/<int:court_id>', methods=['GET', 'POST'])
@login_required
def edit_court(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.list_courts'))

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
        return redirect(url_for('main.list_courts'))

    return render_template('edit_court.html', court=court)

@main_bp.route('/view_court_details/<int:court_id>')
@login_required
def view_court_details(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    court = Court.query.get_or_404(court_id)
    
    total_cases = len(court.cases)
    active_cases = [case for case in court.cases if case.status == CaseStatus.active]
    inactive_cases = [case for case in court.cases if case.status == CaseStatus.inactive]
    finished_cases = [case for case in court.cases if case.status == CaseStatus.finished]
    
    recent_cases = Case.query.filter_by(court_id=court_id).order_by(Case.added_date.desc()).limit(10).all()
    
    display_cases = DisplayCase.query.join(Case).filter(Case.court_id == court_id).all()
    
    return render_template('court_details.html', 
                         court=court,
                         total_cases=total_cases,
                         active_cases=active_cases,
                         inactive_cases=inactive_cases,
                         finished_cases=finished_cases,
                         recent_cases=recent_cases,
                         display_cases=display_cases)

@main_bp.route('/court_cases/<int:court_id>')
@login_required
def court_cases(court_id):
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    court = Court.query.get_or_404(court_id)
    
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    
    query = Case.query.filter_by(court_id=court_id)
    
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

@main_bp.route('/statistics')
@login_required
def statistics():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.index'))
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    court_id = request.args.get('court_id')
    
    case_query = Case.query
    activity_query = ActivityLog.query
    
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
    
    all_cases = case_query.all()
    
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
    
    status_distribution = [
        summary['active_cases'],
        summary['inactive_cases'],
        summary['postponed_cases'],
        summary['finished_cases']
    ]
    
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
    
    courts = Court.query.filter_by(is_active=True).all()
    court_statistics = []
    
    for court in courts:
        court_cases = [c for c in all_cases if c.court_id == court.id]
        total = len(court_cases)
        active = len([c for c in court_cases if c.status == CaseStatus.in_session])
        finished = len([c for c in court_cases if c.status == CaseStatus.finished])
        postponed = len([c for c in court_cases if c.status == CaseStatus.postponed])
        
        completion_rate = round((finished / total * 100), 1) if total > 0 else 0
        
        finished_cases_list = [c for c in court_cases if c.status == CaseStatus.finished and c.case_date]
        avg_duration = 0
        if finished_cases_list:
            total_days = sum([(datetime.now().date() - c.case_date).days for c in finished_cases_list])
            avg_duration = round(total_days / len(finished_cases_list))
        
        court_statistics.append({
            'court_name': court.name,
            'total_cases': total,
            'active_cases': active,
            'finished_cases': finished,
            'postponed_cases': postponed,
            'completion_rate': completion_rate,
            'avg_duration': avg_duration
        })
    
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
    
    recent_activities = ActivityLog.query.order_by(
        ActivityLog.created_at.desc()
    ).limit(10).all()
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    status_changes = ActivityLog.query.filter(
        ActivityLog.action == 'Status Changed',
        ActivityLog.created_at >= thirty_days_ago
    ).all()
    
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

@main_bp.route('/export_report/<format>')
@login_required
def export_report(format):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.index'))
    
    if format == 'excel':
        return export_excel_report()
    elif format == 'pdf':
        flash('PDF export feature coming soon', 'info')
        return redirect(url_for('main.statistics'))
    else:
        flash('Invalid export format', 'danger')
        return redirect(url_for('main.statistics'))

def export_excel_report():
    try:
        import pandas as pd
        from io import BytesIO
        
        output = BytesIO()
        
        cases = Case.query.all()
        activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(1000).all()
        
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
        return redirect(url_for('main.statistics'))
    except Exception as e:
        flash(f'Error exporting Excel: {str(e)}', 'danger')
        return redirect(url_for('main.statistics'))

@main_bp.route('/control')
@login_required
def control():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('main.index'))
    users = User.query.all()
    cases = Case.query.all()
    return render_template('control.html', users=users, cases=cases)

@main_bp.route('/drop_all_tables_confirm')
@login_required
def drop_all_tables_confirm_page():
     if not current_user.is_admin:
          flash('Access denied.', 'danger')
          return redirect(url_for('main.index'))
     return render_template('confirm_drop.html')

@main_bp.route('/drop_all_tables_execute', methods=['POST'])
@login_required
def drop_all_tables_execute():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    confirmation_text = request.form.get('confirmation_text')
    if confirmation_text != "CONFIRM DELETE ALL DATA":
         flash('Incorrect confirmation text. Database reset aborted.', 'danger')
         return redirect(url_for('main.drop_all_tables_confirm_page'))

    print("!!! EXECUTING DROP ALL TABLES !!!")
    try:
        db.drop_all()
        db.create_all()
        flash('All database tables dropped and recreated.', 'warning')

        create_defaults()
        flash('Default admin user and display settings initialized.', 'info')

    except Exception as e:
        flash(f'Error during database reset: {str(e)}', 'danger')
        db.session.rollback()

    return redirect(url_for('main.index'))

def create_defaults():
     if not User.query.first():
         from werkzeug.security import generate_password_hash
         admin = User(
             username='admin',
             password=generate_password_hash('admin123'),
             name='Administrator',
             email='admin@example.com',
             tel='123456789',
             is_admin=True
         )
         db.session.add(admin)
         print("Default admin user created: admin / admin123")

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
         default_visible = ['case_number', 'next_session_date', 'case_subject',
                            'plaintiff', 'defendant', 'status']
         case_fields = [column.name for column in Case.__table__.columns if column.name != 'id']

         for field_name in case_fields:
             if not DisplaySettings.query.filter_by(field_name=field_name).first():
                 setting = DisplaySettings(
                     field_name=field_name,
                     field_name_ar=default_field_map.get(field_name, field_name.replace('_', ' ').title()),
                     is_visible=(field_name in default_visible)
                 )
                 db.session.add(setting)
         print("Default display settings created.")

     try:
          if db.session.new or db.session.dirty:
               db.session.commit()
     except Exception as e:
          db.session.rollback()
          print(f"Error committing defaults: {e}")
