from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from urllib.parse import urlparse
from sqlalchemy import extract
from app.models.models import Case, CaseStatus, Court, User
from extensions import db
from app.utils.helpers import log_activity
from . import cases_bp


@cases_bp.route('/cases')
@login_required
def list_cases():
    try:
        sort_by = request.args.get('sort_by', 'all')
        selected_date = request.args.get('date')
        selected_month = request.args.get('month')
        selected_year = request.args.get('year')
        case_number_search = request.args.get('case_number')
        
        if current_user.is_admin:
            query = Case.query.outerjoin(Court).outerjoin(User)

        else:
            if not current_user.court_id:
                flash('No court assigned to your account.', 'danger')
                return redirect(url_for('main.index'))
            query = Case.query.filter(
                (Case.court_id == current_user.court_id) & 
                (Case.user_id == current_user.id)
            )

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
        status_options = list(CaseStatus)

        return render_template(
            'cases.html',
            cases=cases,
            status_options=status_options
        )
    except Exception as e:
        print(f"Error fetching data for /cases: {e}")
        import traceback
        print(traceback.format_exc())
        flash("An error occurred while loading the cases page.", "danger")
        return redirect(url_for('main.index'))

@cases_bp.route('/add_case', methods=['GET', 'POST'])
@login_required
def add_case():
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to add cases.', 'info')
        return redirect(url_for('auth.list_users'))

    if request.method == 'POST':
        highest_order = (
            db.session.query(db.func.max(Case.c_order))
            .filter(Case.court_id == current_user.court_id)
            .scalar()
        )

        next_order = 1 if highest_order is None else highest_order + 1

        case_number = request.form.get('case_number')
        if not case_number:
             flash('Case Number is required.', 'danger')
             return render_template('add_case.html', form_data=request.form)
        if Case.query.filter_by(case_number=case_number).first():
             flash(f'Case Number "{case_number}" already exists.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        try:
            case_date_str = request.form.get('case_date')
            case_date = datetime.strptime(case_date_str, '%Y-%m-%d').date() if case_date_str else None
        except ValueError:
             flash('Invalid Case Date format. Please use YYYY-MM-DD.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        try:
             num_sessions = int(request.form.get('num_sessions', 1))
             if num_sessions < 0: raise ValueError("Cannot be negative")
        except (ValueError, TypeError):
             flash('Invalid Number of Sessions. Please enter a valid non-negative integer.', 'danger')
             return render_template('add_case.html', form_data=request.form)

        try:
            if 'status_checkbox' in request.form and request.form['status_checkbox'] == 'active':
                 status_enum = CaseStatus.active
            else:
                 status_enum = CaseStatus.inactive
        except ValueError:
             status_enum = CaseStatus.inactive

        try:
            case = Case(
                case_number=case_number,
                case_date=case_date,
                c_order=next_order,
                next_session_date=request.form.get('next_session_date') or None,
                session_result=request.form.get('session_result'),
                num_sessions=num_sessions,
                case_subject=request.form.get('case_subject'),
                defendant=request.form.get('defendant'),
                plaintiff=request.form.get('plaintiff'),
                prosecution_number=request.form.get('prosecution_number'),
                police_department=request.form.get('police_department'),
                police_case_number=request.form.get('police_case_number'),
                status=status_enum,
                court_id=current_user.court_id,
                user_id=current_user.id
            )
            db.session.add(case)
            db.session.commit()
            
            log_activity(
                action='Case Added',
                details=f'Added case {case_number}: {case.case_subject}',
                case_id=case.id,
                court_id=current_user.court_id
            )
            
            flash(f'Case "{case.case_number}" added successfully.', 'success')
            return redirect(url_for('cases.list_cases'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding case: {str(e)}', 'danger')
            return render_template('add_case.html', form_data=request.form)

    return render_template('add_case.html')

@cases_bp.route('/edit_case/<int:case_id>', methods=['GET', 'POST'])
@login_required
def edit_case(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('cases.list_cases'))

    if request.method == 'POST':
        new_case_number = request.form.get('case_number')
        if new_case_number != case.case_number:
             if not new_case_number:
                  flash('Case Number cannot be empty.', 'danger')
                  return render_template('edit_case.html', case=case)
             existing = Case.query.filter(Case.case_number == new_case_number, Case.id != case_id).first()
             if existing:
                  flash(f'Case Number "{new_case_number}" already exists.', 'danger')
                  return render_template('edit_case.html', case=case)
             case.case_number = new_case_number

        try:
             case_date_str = request.form.get('case_date')
             case.case_date = datetime.strptime(case_date_str, '%Y-%m-%d').date() if case_date_str else None
             case.num_sessions = int(request.form.get('num_sessions', 1))
             if case.num_sessions < 0: raise ValueError("Num sessions cannot be negative")
        except (ValueError, TypeError):
             flash('Invalid date or number format provided.', 'danger')
             return render_template('edit_case.html', case=case)

        status_str = request.form.get('status', case.status.value)
        try:
            case.status = CaseStatus(status_str.lower())
        except ValueError:
            flash(f'Invalid status "{status_str}" provided, keeping original.', 'warning')

        case.next_session_date = request.form.get('next_session_date') or None
        case.session_result = request.form.get('session_result')
        case.case_subject = request.form.get('case_subject')
        case.defendant = request.form.get('defendant')
        case.plaintiff = request.form.get('plaintiff')
        case.prosecution_number = request.form.get('prosecution_number')
        case.police_department = request.form.get('police_department')
        case.police_case_number = request.form.get('police_case_number')

        try:
            db.session.commit()
            flash(f'Case "{case.case_number}" updated successfully.', 'success')
            return redirect(url_for('cases.list_cases'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating case: {str(e)}', 'danger')

    return render_template('edit_case.html', case=case)

@cases_bp.route('/delete_case/<int:case_id>', methods=['POST'])
@login_required
def delete_case(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('cases.list_cases'))

    try:
        deleted_order = case.c_order
        case_number = case.case_number

        db.session.delete(case)

        cases_to_update = (
            Case.query.filter(
                Case.court_id == current_user.court_id,
                Case.c_order > deleted_order
            )
            .order_by(Case.c_order.asc())
            .all()
        )

        for c in cases_to_update:
            c.c_order -= 1

        db.session.commit()
        
        log_activity(
            action='Case Deleted',
            details=f'Deleted case {case_number}',
            court_id=current_user.court_id
        )
        
        flash(f'Case "{case_number}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting case: {str(e)}', 'danger')

    return redirect(url_for('cases.list_cases'))

@cases_bp.route('/change_status/<int:case_id>/<string:status>')
@login_required
def change_status(case_id, status):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('cases.list_cases'))

    try:
        old_status = case.status.value if case.status else 'unknown'
        new_status_enum = CaseStatus(status.lower().replace('_', ' '))
        case.status = new_status_enum
        db.session.commit()
        
        log_activity(
            action='Status Changed',
            details=f'Changed status from {old_status} to {new_status_enum.value}',
            case_id=case.id,
            court_id=case.court_id
        )
        
        flash(f'Case "{case.case_number}" status updated to "{new_status_enum.value}".', 'success')
    except ValueError:
        flash(f'Invalid status value provided: "{status}".', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred updating status: {str(e)}', 'danger')

    referrer = request.referrer
    if referrer and urlparse(referrer).path == url_for('cases.list_cases'):
         return redirect(url_for('cases.list_cases'))

    return redirect(url_for('cases.list_cases'))

@cases_bp.route('/delete_selected_cases', methods=['POST'])
@login_required
def delete_selected_cases():
    case_ids_to_delete_str = request.form.getlist('selected_case_ids')

    if not case_ids_to_delete_str:
        flash('No cases were selected for deletion.', 'warning')
        return redirect(url_for('cases.list_cases'))

    case_ids_to_delete = []
    invalid_ids = []
    for id_str in case_ids_to_delete_str:
        try:
            case_ids_to_delete.append(int(id_str))
        except ValueError:
            invalid_ids.append(id_str)

    if invalid_ids:
        flash(f"Invalid case IDs received: {', '.join(invalid_ids)}. Deletion aborted.", 'danger')
        return redirect(url_for('cases.list_cases'))

    deleted_count = 0
    deleted_case_numbers = []
    try:
        query = Case.query.filter(Case.id.in_(case_ids_to_delete))
        
        # Apply permission filters
        if not current_user.is_admin:
            if not current_user.court_id:
                flash('No court assigned to your account.', 'danger')
                return redirect(url_for('cases.list_cases'))
            query = query.filter(Case.court_id == current_user.court_id)

        cases_to_delete = query.all()

        if not cases_to_delete:
            flash('No cases found or you do not have permission to delete them.', 'warning')
            return redirect(url_for('cases.list_cases'))

        # Store case numbers for logging before deletion
        for case in cases_to_delete:
            deleted_case_numbers.append(case.case_number)
            db.session.delete(case)
            deleted_count += 1

        db.session.commit()
        
        # Log activity for bulk deletion
        log_activity(
            action='Bulk Case Deletion',
            details=f'Deleted {deleted_count} case(s): {", ".join(deleted_case_numbers[:5])}{"..." if len(deleted_case_numbers) > 5 else ""}',
            court_id=current_user.court_id
        )
        
        flash(f'Successfully deleted {deleted_count} case(s).', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred during deletion: {str(e)}', 'danger')

    return redirect(url_for('cases.list_cases'))
