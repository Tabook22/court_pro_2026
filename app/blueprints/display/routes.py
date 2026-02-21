from flask import current_app, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models.models import Case, DisplayCase, DisplaySettings, Court, CaseStatus
from extensions import db, sse


def _publish_display_update(payload):
    if not current_app.config.get('SSE_ENABLED'):
        return
    try:
        sse.publish(payload, type='display_update')
    except Exception as sse_error:
        print(f"Warning: Failed to publish SSE event: {sse_error}")
from . import display_bp


@display_bp.route('/manage_display')
@login_required
def manage_display():
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to manage display.', 'info')
        return redirect(url_for('auth.list_users'))

    all_cases = Case.query.filter_by(court_id=current_user.court_id).order_by(Case.case_number).all()

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

@display_bp.route('/add_to_display/<int:case_id>', methods=['POST'])
@login_required
def add_to_display(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    case = Case.query.filter_by(id=case_id, court_id=current_user.court_id).first()
    if not case:
        flash('Case not found or access denied.', 'danger')
        return redirect(url_for('display.manage_display'))

    if DisplayCase.query.filter_by(case_id=case_id).first():
        flash(f'Case "{case.case_number}" is already in the display list.', 'warning')
    else:
        highest_order = db.session.query(db.func.max(DisplayCase.display_order)).scalar()
        next_order = 1 if highest_order is None else highest_order + 1

        display_case = DisplayCase(
            case_id=case_id,
            court_id=current_user.court_id,
            display_order=next_order,
            custom_order=None
        )
        db.session.add(display_case)
        db.session.commit()
        _publish_display_update({"update_type": "add", "case_id": case_id})
        flash(f'Case "{case.case_number}" added to display.', 'success')


    return redirect(url_for('display.manage_display'))

@display_bp.route('/remove_from_display/<int:case_id>', methods=['POST'])
@login_required
def remove_from_display(case_id):
    if not current_user.court_id:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))

    display_case = DisplayCase.query.join(Case).filter(
        DisplayCase.case_id == case_id,
        Case.court_id == current_user.court_id
    ).first()

    display_case = DisplayCase.query.filter_by(case_id=case_id).first()
    if display_case:
        case_number = display_case.case.case_number
        db.session.delete(display_case)
        db.session.commit()

        remaining_display_cases = DisplayCase.query.order_by(DisplayCase.display_order.asc()).all()
        for i, dc in enumerate(remaining_display_cases):
             dc.display_order = i + 1

        db.session.commit()
        _publish_display_update({"update_type": "remove", "case_id": case_id})
        flash(f'Case "{case_number}" removed from display and list reordered.', 'success')

    else:
        flash('Case not found in display list.', 'warning')

    return redirect(url_for('display.manage_display'))

@display_bp.route('/update_display_order', methods=['POST'])
@login_required
def update_display_order():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    updated_count = 0
    try:
        for key, value in request.form.items():
            if key.startswith('order_'):
                try:
                    case_id = int(key.split('_')[1])
                    order_val_str = value.strip()
                    custom_order = int(order_val_str) if order_val_str else None

                    if custom_order is not None and custom_order < 1:
                         flash(f'Invalid order value "{order_val_str}" for case ID {case_id}. Must be 1 or greater. Skipping.', 'warning')
                         continue

                    display_case = DisplayCase.query.filter_by(case_id=case_id).first()
                    if display_case and display_case.custom_order != custom_order:
                        display_case.custom_order = custom_order
                        updated_count += 1
                except (ValueError, IndexError, TypeError):
                    flash(f'Invalid order input received: {key}={value}', 'warning')

        if updated_count > 0:
              db.session.commit()
              _publish_display_update({"update_type": "order", "message": "Display order changed"})
              flash(f'Display order updated for {updated_count} case(s).', 'success')

        else:
             flash('No changes detected in display order.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating display order: {str(e)}', 'danger')

    return redirect(url_for('display.manage_display'))

@display_bp.route('/reorder_display/<int:case_id>/<string:direction>', methods=['POST'])
@login_required
def reorder_display(case_id, direction):
    flash('Button-based reordering is disabled. Please use manual order input.', 'warning')
    return redirect(url_for('display.manage_display'))

@display_bp.route('/display_settings', methods=['GET', 'POST'])
@login_required
def display_settings():
    if not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    default_field_map = {
        "id": "المعرف",
        "case_number": "رقم الدعوى",
        "case_date": "تاريخ الدعوى",
        "added_date": "تاريخ الإضافة",
        "c_order": "الترتيب",
        "next_session_date": "تاريخ الجلسة القادمة",
        "session_result": "نتيجة الجلسة",
        "num_sessions": "رقم الجلسة",
        "case_subject": "موضوع الدعوى",
        "defendant": "المستأنف ضده",
        "plaintiff": "المستأنف",
        "prosecution_number": "الرقم المقابل",
        "police_department": "مركز الشرطة",
        "police_case_number": "رقم الشرطة",
        "status": "الحالة"
    }
    case_fields = [column.name for column in Case.__table__.columns if column.name != 'id']

    if request.method == 'POST':
        visible_field_names = request.form.getlist('visible_fields')
        try:
            for field_name in case_fields:
                setting = DisplaySettings.query.filter_by(field_name=field_name).first()
                current_ar_name = setting.field_name_ar if setting else default_field_map.get(field_name, '')
                field_name_ar = request.form.get(f'field_name_ar_{field_name}', current_ar_name)

                if setting:
                    setting.is_visible = (field_name in visible_field_names)
                    setting.field_name_ar = field_name_ar
                else:
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
        return redirect(url_for('display.display_settings'))

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

    return render_template('settings.html', fields=fields_for_template)

@display_bp.route('/general')
def general():
    court_id = current_user.court_id if current_user.is_authenticated else request.args.get('court_id', type=int)

    if not court_id:
        court_id = 1

    court = Court.query.get(court_id)
    if not court:
        court = Court.query.filter_by(is_active=True).first()
        if not court:
            return "No active courts available for display", 404
        court_id = court.id

    display_entries = DisplayCase.query.join(Case).filter(
        Case.court_id == court_id
    ).options(db.joinedload(DisplayCase.case)).order_by(
        DisplayCase.custom_order.asc().nullsfirst(),
        DisplayCase.display_order.asc()
    ).all()

    cases_to_display = [dc.case for dc in display_entries if dc.case and dc.case.court_id == court_id]

    settings = DisplaySettings.query.all()
    visible_fields = [s.field_name for s in settings if s.is_visible]
    field_translations = {s.field_name: s.field_name_ar for s in settings if s.field_name_ar}

    if not visible_fields:
        visible_fields = ['case_number', 'next_session_date', 'case_subject', 'plaintiff', 'defendant', 'status']
        default_translations = {
            "case_number": "رقم الدعوى", "next_session_date": "الجلسة القادمة",
            "case_subject": "الموضوع", "plaintiff": "المستأنف",
            "defendant": "المستأنف ضده", "status": "الحالة"
        }
        matching_fields = {field: default_translations.get(field, field.replace('_', ' ').title()) for field in visible_fields}
    else:
        matching_fields = {field: field_translations.get(field, field.replace('_', ' ').title()) for field in visible_fields}

    # URL for QR code: always point to this specific court so scanners get the same court
    qr_target_url = url_for('display.general', court_id=court.id, _external=True)

    return render_template(
        'general.html',
        court=court,
        cases=cases_to_display,
        visible_fields=visible_fields,
        matching_fields=matching_fields,
        qr_target_url=qr_target_url
    )


@display_bp.route('/general_control')
@login_required
def general_control():
    if not current_user.court_id and not current_user.is_admin:
        flash('No court assigned to your account.', 'danger')
        return redirect(url_for('main.index'))
    
    if current_user.is_admin and not current_user.court_id:
        flash('Please impersonate a user with court assignment to control display.', 'info')
        return redirect(url_for('auth.list_users'))

    try:
        display_entries = DisplayCase.query.join(Case).filter(
            Case.court_id == current_user.court_id
        ).options(db.joinedload(DisplayCase.case)).order_by(
            DisplayCase.custom_order.asc().nullslast(),
            DisplayCase.display_order.asc()
        ).all()
        cases_to_display = [dc for dc in display_entries if dc.case]

        status_options = list(CaseStatus)

        return render_template(
            'general_control.html',
            display_entries=cases_to_display,
            status_options=status_options
        )

    except Exception as e:
         print(f"Error fetching data for /general_control: {e}")
         import traceback
         print(traceback.format_exc())
         flash("An error occurred while loading the case reorder page.", "danger")
         return redirect(url_for('main.index'))

@display_bp.route('/update_display_order_ajax', methods=['POST'])
@login_required
def update_display_order_ajax():
    if not current_user.court_id:
        return jsonify({'success': False, 'message': 'No court assigned to your account'}), 403

    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request: Content-Type must be application/json'}), 400

    data = request.get_json()
    ordered_case_ids_str = data.get('order')

    if not isinstance(ordered_case_ids_str, list):
        return jsonify({'success': False, 'message': 'Invalid data format: "order" array not found or not a list.'}), 400

    ordered_case_ids = []
    for idx, case_id_str in enumerate(ordered_case_ids_str):
        try:
            ordered_case_ids.append(int(case_id_str))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': f'Invalid case ID format found at position {idx}: {case_id_str}. Expected integers.'}), 400

    if not ordered_case_ids:
        return jsonify({'success': True, 'message': 'Received empty order list. No changes made.'})

    try:
        display_cases_dict = {dc.case_id: dc for dc in DisplayCase.query.filter(DisplayCase.case_id.in_(ordered_case_ids)).all()}

        updated_count = 0
        for index, case_id in enumerate(ordered_case_ids):
            new_order = index + 1

            display_case = display_cases_dict.get(case_id)
            if display_case:
                if display_case.custom_order != new_order:
                    display_case.custom_order = new_order
                    updated_count += 1
            else:
                print(f"Warning: Case ID {case_id} received from frontend but not found in DisplayCase table during reorder.")

        if updated_count > 0:
            db.session.commit()
            message = f'Successfully updated order for {updated_count} case(s).'
            
            try:
                 _publish_display_update({"update_type": "order", "message": "Display order changed"})

            except Exception as sse_error:
                 print(f"Warning: Failed to publish SSE event after order update: {sse_error}")

            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': True, 'message': 'No order changes were necessary.'})

    except Exception as e:
        db.session.rollback()
        print(f"Error updating display order via AJAX: {str(e)}")
        return jsonify({'success': False, 'message': 'A database error occurred while saving the new order.'}), 500
