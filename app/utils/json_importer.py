import os
import json
from datetime import datetime
from app.models.models import Case, CaseStatus

class JsonToDatabase:
    def __init__(self, db_session, court_id, json_storage_path):
        self.db = db_session
        self.court_id = court_id
        self.json_storage_path = json_storage_path

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

    def import_data(self, case_data_list, current_user_id):
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
                    # Validate date first
                    case_date_str = record.get('case_date')
                    case_date_obj = None
                    if case_date_str:
                        try:
                            case_date_obj = datetime.strptime(str(case_date_str), '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass # Keep existing date if invalid? Or fail?

                    # Validate status
                    status_str = record.get('status', 'inactive')
                    try:
                        status_enum = CaseStatus(str(status_str).lower())
                    except ValueError:
                        status_enum = CaseStatus.inactive

                    # Validate integers
                    try:
                        num_sessions = int(record.get('num_sessions', 1))
                    except (ValueError, TypeError):
                        num_sessions = 1

                    existing_case = Case.query.filter_by(case_number=str(case_number), court_id=self.court_id).first()
                    if existing_case:
                        # Update case fields
                        if case_date_obj:
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
                    user_id=current_user_id, # Add user_id for tracking who imported
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
