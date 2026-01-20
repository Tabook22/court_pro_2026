# json_to_db.py

import os
import json
from datetime import datetime, timezone
from models import db, Case

class JsonToDatabase:
    def __init__(self):
        self.default_values = {
            'case_number': 'no data',
            'case_date': datetime.now(timezone.utc).date(),
            'next_session_date': 'no data',
            'session_result': 'no data',
            'num_sessions': 0,
            'case_subject': 'no data',
            'defendant': 'no data',
            'plaintiff': 'no data',
            'prosecution_number': 'no data',
            'police_department': 'no data',
            'police_case_number': 'no data',
            'status': 'inactive'
        }

    def _parse_date(self, date_str):
        """Parse date string to date object"""
        try:
            if not date_str or date_str == 'no data':
                return datetime.now(timezone.utc).date()
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception as e:
            print(f"Error parsing date {date_str}: {str(e)}")
            return datetime.now(timezone.utc).date()

    def import_json_to_db(self, json_data):
        """Import JSON data into the Case table"""
        try:
            # Get the highest existing order
            highest_order = db.session.query(db.func.max(Case.c_order)).scalar()
            next_order = 1 if highest_order is None else highest_order + 1

            # Get the data array from JSON
            records = json_data.get('data', [])
            if not records:
                return {
                    'success': False,
                    'error': 'No data found in JSON file',
                    'message': 'Failed to import cases: No data found'
                }
                
            cases_added = 0
            errors = []

            for index, record in enumerate(records, 1):
                try:
                    # Create new case with default values
                    case_data = self.default_values.copy()
                    
                    # Map JSON fields to Case model fields
                    field_mapping = {
                        'case_number': str(record.get('case_number', 'no data')),
                        'next_session_date': str(record.get('next_session_date', 'no data')),
                        'defendant': str(record.get('defendant', 'no data')),
                        'plaintiff': str(record.get('plaintiff', 'no data')),
                        'prosecution_number': str(record.get('prosecution_number', 'no data'))
                    }

                    # Print debugging information
                    print(f"Processing record {index}:", field_mapping)

                    # Update case_data with mapped values
                    case_data.update(field_mapping)

                    # Create new Case instance
                    new_case = Case(
                        case_number=case_data['case_number'],
                        case_date=self._parse_date(record.get('case_date')),
                        added_date=datetime.now(timezone.utc),
                        c_order=next_order,
                        next_session_date=case_data['next_session_date'],
                        session_result=case_data['session_result'],
                        num_sessions=int(case_data['num_sessions']),
                        case_subject=case_data['case_subject'],
                        defendant=case_data['defendant'],
                        plaintiff=case_data['plaintiff'],
                        prosecution_number=case_data['prosecution_number'],
                        police_department=case_data['police_department'],
                        police_case_number=case_data['police_case_number'],
                        status=case_data['status']
                    )

                    db.session.add(new_case)
                    cases_added += 1
                    next_order += 1

                except Exception as e:
                    error_msg = f"Error processing record {index}: {str(e)}"
                    print(error_msg)
                    errors.append(error_msg)
                    continue

            if cases_added > 0:
                db.session.commit()
                return {
                    'success': True,
                    'cases_added': cases_added,
                    'errors': errors,
                    'message': f'Successfully imported {cases_added} cases'
                }
            else:
                db.session.rollback()
                return {
                    'success': False,
                    'error': 'No cases were added',
                    'errors': errors,
                    'message': 'Failed to import any cases'
                }

        except Exception as e:
            db.session.rollback()
            error_msg = f"Database error: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'message': 'Failed to import cases'
            }

    def process_json_file(self, json_filename, json_storage_path='json_storage'):
        """Process a JSON file and import its contents to the database"""
        try:
            json_path = os.path.join(json_storage_path, json_filename)
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            return self.import_json_to_db(json_data)
            
        except Exception as e:
            return {
                'success': False,
                'cases_added': 0,
                'errors': [str(e)],
                'message': f'Failed to read JSON file: {str(e)}'
            }
    def process_json_file(self, json_filename, json_storage_path='json_storage'):
        """Process a JSON file and import its contents to the database"""
        try:
            json_path = os.path.join(json_storage_path, json_filename)
            print(f"Reading JSON file from: {json_path}")
            
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                
            print("JSON data structure:", json_data.keys())
            print("Number of records:", len(json_data.get('data', [])))
            
            return self.import_json_to_db(json_data)
            
        except Exception as e:
            error_msg = f"Failed to read JSON file: {str(e)}"
            print(error_msg)
            return {
                'success': False,
                'cases_added': 0,
                'error': error_msg,
                'message': error_msg
            }