# excel_processor.py (Modified to remove googletrans)

# Note: Removed 'from googletrans import Translator'
from flask import jsonify # Keep jsonify if used elsewhere, otherwise remove
import pandas as pd
import json
import numpy as np # Keep numpy if needed by pandas or other logic
from datetime import datetime, timezone, date
import os

class ExcelProcessor:
    def __init__(self, json_storage_path='json_storage'):
        """
        Initialize the Excel Processor

        Args:
            json_storage_path (str): Path where JSON files will be stored
        """
        # Note: Removed self.translator = Translator()
        self.json_storage_path = json_storage_path
        # Create storage directory if it doesn't exist
        os.makedirs(json_storage_path, exist_ok=True)

        # Predefined translations for known headers - Comprehensive mapping for all Case model fields
        self.known_translations = {
            # Core fields
            "رقم الدعوى": "case_number",
            "م": "c_order",
            "تاريخ الدعوى": "case_date",
            "تاريخ الإضافة": "added_date",
            
            # Session fields
            "تاريخ الجلسة المقبلة": "next_session_date",
            "تاريخ الجلسة القادمة": "next_session_date",
            "نتيجة الجلسة": "session_result",
            "رقم الجلسة": "num_sessions",
            "عدد الجلسات": "num_sessions",
            
            # Case details
            "موضوع الدعوى": "case_subject",
            "موضوع": "case_subject",
            
            # Parties
            "مستأنف ضده": "defendant",
            "المستأنف ضده": "defendant",
            "المدعى عليه": "defendant",
            "مستأنف": "plaintiff",
            "المستأنف": "plaintiff",
            "المدعي": "plaintiff",
            
            # Prosecution/Police fields
            "الرقم المقابل": "prosecution_number",
            "مركز الشرطة": "police_department",
            "رقم الشرطة": "police_case_number",
            
            # Status
            "الحالة": "status",
            "حالة": "status",
            
            # Common variations and aliases
            "الترتيب": "c_order",
            "ترتيب": "c_order",
        }

    # *** MODIFIED _translate_headers function ***
    def _translate_headers(self, headers):
        """
        Translate headers from Arabic to English using ONLY predefined mappings.
        Unknown headers will be processed to snake_case.

        Args:
            headers (list): List of column headers in Arabic

        Returns:
            dict: Mapping of original headers to translated headers
        """
        translated_headers = {}
        unknown_headers_found = []
        for header in headers:
            header_str = str(header).strip() # Ensure it's a string and remove whitespace
            # Check if header exists in known translations
            if header_str in self.known_translations:
                translated_headers[header] = self.known_translations[header_str]
            else:
                # Fallback for unknown headers: process to snake_case
                processed_header = self._process_header_name(header_str)
                translated_headers[header] = processed_header
                # Log a warning that an unknown header was encountered
                if header_str not in unknown_headers_found: # Log only once per unknown header
                     print(f"Warning: Unknown Excel header encountered: '{header_str}'. Using processed name: '{processed_header}'. Consider adding it to known_translations in excel_processor.py.")
                     unknown_headers_found.append(header_str)
        return translated_headers

    def _process_header_name(self, header):
        """
        Convert header to snake_case and clean it

        Args:
            header (str): Header text to process

        Returns:
            str: Processed header name
        """
        # Remove special characters and convert to lowercase
        processed = ''.join(c.lower() if c.isalnum() else '_' for c in str(header))
        # Replace multiple underscores with single underscore
        processed = '_'.join(filter(None, processed.split('_')))
        # Handle potential leading/trailing underscores after processing
        return processed.strip('_')

    # --- The rest of the functions remain the same ---

    def _detect_column_types(self, df):
        """
        Detect and standardize column types

        Args:
            df (pandas.DataFrame): DataFrame to analyze

        Returns:
            dict: Mapping of column names to their detected types
        """
        type_mapping = {}

        for column in df.columns:
            # Ensure column exists before processing
            if column not in df:
                print(f"Warning: Column '{column}' not found in DataFrame during type detection.")
                continue

            sample_data = df[column].dropna().head(10)  # Check first 10 non-null values

            if len(sample_data) == 0:
                type_mapping[column] = 'string'
                continue

            # Try common date formats
            # Consider making date formats configurable or more robust
            date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y']
            is_date = False

            # Check if pandas already recognized it as datetime
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                 # Check a sample for NaT (Not a Time) which can skew detection
                 if not sample_data.isna().all():
                     type_mapping[column] = 'date'
                     continue

            # Then try parsing strings as dates
            # Only attempt date parsing if the dtype looks like object (string)
            if df[column].dtype == 'object':
                for date_format in date_formats:
                    try:
                        # Attempt conversion on a sample
                        pd.to_datetime(sample_data, format=date_format, errors='raise')
                        # If sample conversion works, assume it's a date column
                        type_mapping[column] = 'date'
                        is_date = True
                        break # Stop checking formats once one works
                    except (ValueError, TypeError):
                        continue # Try next format

            if is_date:
                continue

            # Check if numeric (integer or float)
            try:
                # Attempt numeric conversion on sample, coercing errors to NaN
                numeric_sample = pd.to_numeric(sample_data, errors='coerce')
                # If *all* non-NaN values in the sample are integers after conversion...
                if not numeric_sample.isna().all() and (numeric_sample.dropna() == numeric_sample.dropna().astype(int)).all():
                     # Check if original non-numeric strings exist in sample that became NaN
                     # This avoids classifying "1, 2, Apple" as integer
                     original_non_numeric = sample_data[pd.to_numeric(sample_data, errors='coerce').isna()]
                     if original_non_numeric.empty:
                           type_mapping[column] = 'integer'
                     else:
                           type_mapping[column] = 'string' # Mixed types
                # Check for float (if not purely integer)
                elif not numeric_sample.isna().all():
                     original_non_numeric = sample_data[pd.to_numeric(sample_data, errors='coerce').isna()]
                     if original_non_numeric.empty:
                          type_mapping[column] = 'float'
                     else:
                          type_mapping[column] = 'string' # Mixed types
                else: # All values failed numeric conversion
                    type_mapping[column] = 'string'
            except Exception: # Catch any broad error during numeric check
                type_mapping[column] = 'string'

        return type_mapping


    def _format_value(self, value, column_type):
        """
        Format a value based on its column type for JSON compatibility.

        Args:
            value: The value to format
            column_type (str): The detected type ('date', 'integer', 'float', or 'string')

        Returns:
            Formatted value (string, int, float, None)
        """
        if pd.isna(value):
            return None

        try:
            if column_type == 'date':
                # If pandas read it as datetime, format it
                if isinstance(value, (datetime, pd.Timestamp, date)):
                    # Check if it has time components we want to ignore
                    if hasattr(value, 'hour') and (value.hour != 0 or value.minute != 0 or value.second != 0):
                         # Decide: return full ISO format or just date? Let's return ISO for now.
                         return value.strftime('%Y-%m-%dT%H:%M:%S')
                    else:
                         return value.strftime('%Y-%m-%d')
                else:
                    # Attempt to parse if it's a string that looks like a date but wasn't detected initially
                    try:
                        return pd.to_datetime(str(value)).strftime('%Y-%m-%d')
                    except (ValueError, TypeError):
                         return str(value) # Fallback to string if parsing fails
            elif column_type == 'integer':
                # Convert potential floats (like 5.0) or strings to int
                 return int(float(str(value)))
            elif column_type == 'float':
                return float(str(value))
            else: # String
                return str(value)
        except (ValueError, TypeError, OverflowError) as e:
            # Handle edge cases where conversion might fail
            print(f"Warning: Could not format value '{value}' as type '{column_type}': {e}. Returning as string.")
            return str(value)


    def save_to_json(self, data, original_filename):
        """
        Save processed data to a JSON file

        Args:
            data (dict): Data to save (should contain 'schema' and 'data')
            original_filename (str): Name of the original Excel file

        Returns:
            str: Name of the saved JSON file or None if error
        """
        try:
            # Sanitize original filename for use in JSON filename
            safe_base = "".join(c if c.isalnum() else "_" for c in os.path.splitext(original_filename)[0])
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            # Limit length of base name component
            safe_base = (safe_base[:50]) if len(safe_base) > 50 else safe_base
            json_filename = f"{safe_base}_{timestamp}.json"
            json_path = os.path.join(self.json_storage_path, json_filename)

            # Save the data to JSON file with proper encoding
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str) # Use default=str for tricky types

            return json_filename
        except Exception as e:
            print(f"Error saving data to JSON file '{json_filename}': {str(e)}")
            return None


    def process_excel_file(self, file_path):
        """
        Process the Excel file and return schema and data in JSON format

        Args:
            file_path (str): Path to the Excel file

        Returns:
            dict: Processing results including success status, schema, and data
        """
        try:
            # Read Excel file, handle potential errors during read
            try:
                # Specify engine if needed, especially for .xls
                df = pd.read_excel(file_path, engine='openpyxl' if file_path.endswith('.xlsx') else None)
            except Exception as read_error:
                 print(f"Pandas error reading Excel file '{file_path}': {read_error}")
                 return {'success': False, 'error': f"Failed to read Excel file: {read_error}", 'message': 'Error reading file content.'}

            if df.empty:
                 return {'success': False, 'error': 'Excel file is empty.', 'message': 'No data found in file.'}

            # Strip whitespace from headers
            df.columns = df.columns.map(lambda x: str(x).strip() if x else x)

            # Get original headers and translate them using ONLY known translations
            original_headers = df.columns.tolist()
            translated_headers = self._translate_headers(original_headers) # Modified function

            # Create a mapping of translations for reference
            translation_mapping = {
                original: {
                    'translated': translated,
                    'original': original
                } for original, translated in translated_headers.items()
            }

            # Check for essential columns AFTER potential translation (e.g., case_number)
            essential_cols = ['case_number', 'c_order'] # Add others if needed
            current_cols_set = set(translated_headers.values())
            missing_essential = [col for col in essential_cols if col not in current_cols_set]
            if missing_essential:
                 error_msg = f"Missing essential translated column(s): {', '.join(missing_essential)}. Check Excel headers and known_translations."
                 print(error_msg)
                 return {'success': False, 'error': error_msg, 'message': 'Essential columns missing.'}


            # Rename columns in DataFrame using the translated names
            df.rename(columns=translated_headers, inplace=True)

            # Detect column types based on potentially renamed columns
            column_types = self._detect_column_types(df)

            # Create schema dictionary
            schema = {
                'original_headers': original_headers,
                'translated_headers': translated_headers,
                'column_types': column_types,
                'row_count': len(df),
                'processed_date': datetime.now(timezone.utc).isoformat(),
                'translation_mapping': translation_mapping
            }

            # Convert DataFrame rows to list of dictionaries with formatted values
            data = []
            for index, row in df.iterrows():
                row_dict = {}
                for col_name in df.columns: # Iterate through potentially renamed columns
                    col_type = column_types.get(col_name, 'string') # Default to string if type detection failed
                    row_dict[col_name] = self._format_value(row[col_name], col_type)
                data.append(row_dict)

            # Prepare the final result dictionary
            result_data_to_save = {
                'schema': schema,
                'data': data
            }

            # Save to JSON file
            original_filename = os.path.basename(file_path)
            json_filename = self.save_to_json(result_data_to_save, original_filename)

            if not json_filename: # Check if saving failed
                 return {'success': False, 'error': 'Failed to save processed data to JSON.', 'message': 'Error saving JSON file.'}

            # Log all extracted columns for debugging
            print(f"Excel processing complete:")
            print(f"  - Total columns extracted: {len(df.columns)}")
            print(f"  - Columns: {list(df.columns)}")
            print(f"  - Total rows: {len(df)}")
            print(f"  - Translated headers mapping:")
            for orig, trans in translated_headers.items():
                print(f"    '{orig}' -> '{trans}'")
            
            # Return success payload for the API
            return {
                'success': True,
                'schema': schema,
                # Avoid sending large data back in API response if not needed by client immediately
                # 'data': data,
                'json_filename': json_filename,
                'message': f'File processed successfully. {len(df)} rows and {len(df.columns)} columns extracted. Saved to {json_filename}.',
                'row_count': len(df),
                'column_count': len(df.columns),
                'extracted_columns': list(df.columns)  # Include column names in response
            }

        except pd.errors.EmptyDataError:
             return {'success': False, 'error': 'Excel file is empty or contains no data sheets.', 'message': 'Empty file.'}
        except FileNotFoundError:
             return {'success': False, 'error': f'File not found at path: {file_path}', 'message': 'File not found.'}
        except Exception as e:
            # Catch-all for other unexpected errors during processing
            print(f"Error processing Excel file '{file_path}': {str(e)}")
            import traceback
            print(traceback.format_exc()) # Print full traceback for debugging
            return {
                'success': False,
                'error': f'An unexpected error occurred: {str(e)}',
                'message': 'Error processing file'
            }

    # get_processed_data function remains the same
    def get_processed_data(self, json_filename):
        """
        Retrieve processed data from a saved JSON file

        Args:
            json_filename (str): Name of the JSON file to retrieve

        Returns:
            dict: The processed data or None if file not found
        """
        # Sanitize filename before joining path
        json_filename_safe = secure_filename(json_filename) # Use werkzeug's secure_filename
        if json_filename_safe != json_filename: # Check if filename was changed (potential issue)
             print(f"Warning: Potentially unsafe filename provided: '{json_filename}' -> '{json_filename_safe}'")
             # Decide whether to proceed or reject

        json_path = os.path.join(self.json_storage_path, json_filename_safe)
        if not os.path.exists(json_path):
            print(f"Error: JSON file not found at '{json_path}'")
            return None

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
             print(f"Error: Invalid JSON found in file '{json_path}'")
             return None
        except Exception as e:
            print(f"Error reading JSON file '{json_path}': {str(e)}")
            return None

# Example of using secure_filename if needed (already used in app.py)
from werkzeug.utils import secure_filename