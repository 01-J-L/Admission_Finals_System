
from flask import Blueprint, render_template, request, flash, redirect, session, url_for, jsonify, current_app, Response, send_file
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import datetime
from datetime import timedelta
import base64
import traceback
import secrets
from flask_mail import Message
import os
import io
import secrets # for OTP generation
from datetime import timedelta

# ----------------- BLUEPRINT SETUP -----------------
auth = Blueprint('auth', __name__)

# ----------------- DATABASE CONNECTION -----------------
def get_db_connection():
    try:
        print("--- Attempting to Read DB Environment Variables ---")
        env_db_host_from_os = os.getenv('DB_HOST')
        env_db_user_from_os = os.getenv('DB_USER')
        # For logging actual password existence, not value
        env_db_password_exists_from_os = "Yes" if os.getenv('DB_PASSWORD') else "No"
        env_db_password_from_os = os.getenv('DB_PASSWORD') # Actual password value from env
        env_db_name_from_os = os.getenv('DB_NAME')
        env_db_port_str_from_os = os.getenv('DB_PORT') # Port from env is a string

        print(f"Raw os.getenv('DB_HOST'): {env_db_host_from_os}")
        print(f"Raw os.getenv('DB_USER'): {env_db_user_from_os}")
        print(f"Raw os.getenv('DB_PASSWORD') exists: {env_db_password_exists_from_os}")
        print(f"Raw os.getenv('DB_NAME'): {env_db_name_from_os}")
        print(f"Raw os.getenv('DB_PORT'): {env_db_port_str_from_os}")
        print("--- End of Reading DB Environment Variables ---")

        # Railway specific defaults (derived from typical Railway setups and user-provided connection string)
        RAILWAY_DEFAULT_HOST = 'crossover.proxy.rlwy.net'
        RAILWAY_DEFAULT_USER = 'root'
        RAILWAY_DEFAULT_PASSWORD = "jSFbqIMVIpKfAFdoGTampFzDSaJEkvtO"
        RAILWAY_DEFAULT_DB_NAME = "railway" # As per user's connection string example
        RAILWAY_DEFAULT_PORT_STR = '36284' # As per user's connection string example
        
        # Determine effective DB host
        db_host = env_db_host_from_os
        if env_db_host_from_os and env_db_host_from_os.lower() == 'localhost':
            print(f"Warning: DB_HOST from environment is '{env_db_host_from_os}'. This is often incorrect for a remote Railway database. "
                  f"Overriding to use the default Railway proxy host: '{RAILWAY_DEFAULT_HOST}'.")
            db_host = RAILWAY_DEFAULT_HOST
        elif not env_db_host_from_os:
            print(f"DB_HOST not set in environment. Using default Railway proxy host: '{RAILWAY_DEFAULT_HOST}'.")
            db_host = RAILWAY_DEFAULT_HOST
        # If env_db_host_from_os is set and is not 'localhost', it will be used as db_host.

        # Determine other connection parameters: use environment variable if set, otherwise Railway default.
        db_user = env_db_user_from_os or RAILWAY_DEFAULT_USER
        db_password = env_db_password_from_os or RAILWAY_DEFAULT_PASSWORD
        db_name = env_db_name_from_os or RAILWAY_DEFAULT_DB_NAME
        
        # Determine effective port: use port string from environment if set, else Railway default port string.
        # Then convert to int, with a final fallback to a known valid integer (Railway's default port).
        effective_port_str = env_db_port_str_from_os or RAILWAY_DEFAULT_PORT_STR
        
        db_port = int(RAILWAY_DEFAULT_PORT_STR) # Initialize with a known valid integer from Railway default
        try:
            db_port = int(effective_port_str)
        except (ValueError, TypeError):
            # This message is critical if effective_port_str (which could be from env) is bad.
            # If it was already using RAILWAY_DEFAULT_PORT_STR and failed, that's a bigger issue (e.g. misconfigured default).
            print(f"CRITICAL: The determined DB_PORT string ('{effective_port_str}') is not a valid integer. "
                  f"Falling back to the default Railway port number: {RAILWAY_DEFAULT_PORT_STR}.")
            # db_port is already set to int(RAILWAY_DEFAULT_PORT_STR), so no change needed here for the fallback.
        
        print(f"Attempting DB connection with: Host='{db_host}', Port={db_port}, User='{db_user}', Database='{db_name}'")

        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=db_port
        )
        print("Database connection successful.")
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        traceback.print_exc()
        return None

# ----------------- FILE PROCESSING HELPER -----------------
def process_uploaded_file(file_storage, file_description_for_error, max_size_mb=5):
    if file_storage and file_storage.filename != '':
        filename = secure_filename(file_storage.filename)
        mimetype = file_storage.mimetype

        allowed_mimetypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        file_ext = os.path.splitext(filename)[1].lower()

        if not (mimetype in allowed_mimetypes or file_ext in allowed_extensions):
             return None, None, None, f"Invalid file type for {file_description_for_error} ('{filename}'). Allowed: PDF, JPG, PNG."

        file_storage.seek(0, os.SEEK_END)
        file_length = file_storage.tell()
        file_storage.seek(0)

        if file_length == 0:
            return None, None, None, f"{file_description_for_error} ('{filename}') is empty. Please upload a valid file."

        if file_length > max_size_mb * 1024 * 1024:
            return None, None, None, f"{file_description_for_error} ('{filename}') is too large (max {max_size_mb}MB)."

        file_data = file_storage.read()
        return file_data, filename, mimetype, None
    return None, None, None, None

# ----------------- EMAIL otp -----------------

def send_otp_email(user_email, otp_code):
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    subject = f"Verify Your PGPC Account - OTP: {otp_code} - {sender_name_from_config}"
    
    try:
        verify_url = url_for('auth.verify_otp_page', _external=True) 
    except RuntimeError:
        verify_url = f"{current_app.config.get('PREFERRED_URL_SCHEME', 'http')}://{current_app.config.get('SERVER_NAME', 'your-domain.com')}/verify-otp"
        if 'your-domain.com' in verify_url: print("Warning: SERVER_NAME might not be correctly set for OTP email links (verify_url).")

    try:
        html_body = render_template(
            'email/otp_verification_email.html',
            user_email=user_email,
            otp_code=otp_code,
            verify_url=verify_url,
            sender_name=sender_name_from_config,
            now=datetime.datetime.now()
        )
    except Exception as e_template:
        print(f"CRITICAL: Email template 'email/otp_verification_email.html' not found or error rendering. Error: {e_template}")
        html_body = f"<p>Dear User,</p><p>Your One-Time Password (OTP) for account verification is: <strong>{otp_code}</strong>. Please enter this OTP on the verification page. This OTP is valid for 10 minutes.</p><p>If you didn't request this, please ignore this email.</p>"
        
    email_sent = _send_email(subject, [user_email], html_body, sender_name_override=sender_name_from_config)
    return email_sent

# ----------------- EMAIL SENDING HELPER FUNCTIONS -----------------

def _send_email(subject, recipients, html_body, sender_name_override=None):
    mail_handler = current_app.extensions.get('mail')
    if not mail_handler:
        print("CRITICAL: Flask-Mail is not configured or initialized. Email not sent.")
        return False
    if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
        print("CRITICAL: MAIL_USERNAME or MAIL_PASSWORD not configured. Email not sent.")
        return False

    effective_sender_name = sender_name_override or current_app.config.get('MAIL_SENDER_NAME')
    default_sender_config = current_app.config.get('MAIL_DEFAULT_SENDER')
    sender_email_address = None

    if isinstance(default_sender_config, tuple):
        sender_email_address = default_sender_config[1]
        if not effective_sender_name: effective_sender_name = default_sender_config[0]
    elif isinstance(default_sender_config, str):
        sender_email_address = default_sender_config

    if not sender_email_address:
        sender_email_address = current_app.config.get('MAIL_USERNAME')
        print(f"Warning: MAIL_DEFAULT_SENDER not fully configured, using MAIL_USERNAME ({sender_email_address}) as sender email.")
    if not effective_sender_name: effective_sender_name = "PGPC System"

    final_sender = (effective_sender_name, sender_email_address) if effective_sender_name else sender_email_address

    try:
        msg = Message(subject=subject, sender=final_sender, recipients=recipients, html=html_body)
        mail_handler.send(msg)
        print(f"Email '{subject}' successfully dispatched to {recipients}.")
        return True
    except Exception as e_mail_send:
        print(f"CRITICAL: Failed to send email '{subject}' to {recipients}. Error: {e_mail_send}")
        traceback.print_exc()
        return False

def send_application_status_email(applicant_email, applicant_name, new_status, application_id, program_choice=None, exam_status=None):
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    app_id_formatted = f"P2025{application_id:04d}"
    subject, template_name = "", ""
    email_context = {
        'applicant_name': applicant_name, 'application_id_formatted': app_id_formatted,
        'program_choice': program_choice, 'sender_name': sender_name_from_config,
        'now': datetime.datetime.now(), 'exam_status': exam_status, 'application_status': new_status
    }

    status_map = {
        'Approved': ('email/application_approved_email.html', f"Application {app_id_formatted} Approved"),
        'Rejected': ('email/application_rejected_email.html', f"Application {app_id_formatted} Update"),
        'Passed': ('email/application_passed_email.html', f"Congratulations! Application {app_id_formatted} Processed: Passed"),
        'Failed': ('email/application_failed_email.html', f"Application {app_id_formatted} Processed: Failed"),
    }
    exam_status_map = {
        'Passed': ('email/exam_passed_email.html', f"Admission Exam Result for {app_id_formatted}"),
        'Failed': ('email/exam_failed_email.html', f"Admission Exam Result for {app_id_formatted}"),
    }

    if new_status in status_map:
        template_name, base_subject = status_map[new_status]
        subject = base_subject
        if new_status == 'Approved' and exam_status == 'Passed':
            subject = f"Congratulations! Application {app_id_formatted} Approved & Exam Passed"
        elif new_status == 'Rejected' and exam_status == 'Failed':
            subject = f"Application {app_id_formatted} Update (Exam Result)"
        subject += f" - {sender_name_from_config}"
    elif exam_status in exam_status_map and new_status not in status_map:
        template_name, subject_base = exam_status_map[exam_status]
        subject = f"{subject_base} - {sender_name_from_config}"
    else:
        print(f"Email not sent: Status '{new_status}' or exam_status '{exam_status}' no primary notification for {app_id_formatted}.")
        return False

    try:
        html_body = render_template(template_name, **email_context)
    except Exception as e_template:
        print(f"CRITICAL: Email template '{template_name}' not found or error rendering. Error: {e_template}")
        # Basic fallback (consider enhancing if templates are critical)
        html_body = f"<p>Dear {applicant_name},</p><p>There is an update on your application {app_id_formatted}. Status: {new_status}. Exam: {exam_status or 'N/A'}.</p>"

    return _send_email(subject, [applicant_email], html_body, sender_name_override=sender_name_from_config)

def send_password_reset_email(user_email, token):
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    try:
        reset_url = url_for('auth.reset_password_page', token=token, _external=True)
    except RuntimeError as e:
        print(f"CRITICAL: Cannot generate external reset URL. Error: {e}")
        return False, None

    subject = f"Password Reset Request - {sender_name_from_config}"
    html_body = render_template('email/reset_password_email.html', reset_url=reset_url, user_email=user_email, sender_name=sender_name_from_config, now=datetime.datetime.now())
    email_sent = _send_email(subject, [user_email], html_body, sender_name_override=sender_name_from_config)
    return email_sent, reset_url

def send_admin_created_account_email(user_email, user_full_name, temporary_password):
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    try:
        login_url = url_for('auth.student_login_page', _external=True)
    except RuntimeError as e:
        print(f"CRITICAL: Cannot generate external login URL for admin-created account email. Error: {e}")
        login_url = f"{current_app.config.get('PREFERRED_URL_SCHEME', 'http')}://{current_app.config.get('SERVER_NAME', 'your-domain.com')}/student-login"
        if 'your-domain.com' in login_url: print("Warning: SERVER_NAME might not be correctly set for email links.")

    subject = f"Your PGPC Student Account Has Been Created - {sender_name_from_config}"
    try:
        html_body = render_template('email/admin_created_account_email.html', user_full_name=user_full_name, user_email=user_email, temporary_password=temporary_password, login_url=login_url, sender_name=sender_name_from_config, now=datetime.datetime.now())
    except Exception as e_template:
        print(f"CRITICAL: Email template 'email/admin_created_account_email.html' not found or error rendering. Error: {e_template}")
        html_body = f"<p>Dear {user_full_name},</p><p>An account has been created for you. Email: {user_email}, Temp Password: {temporary_password}. Login: <a href='{login_url}'>{login_url}</a></p>"
    return _send_email(subject, [user_email], html_body, sender_name_override=sender_name_from_config)

# ----------------- ADMIN ROUTES -----------------
@auth.route('/admin/application/<int:applicant_id>/notes', methods=['POST'])
def admin_save_application_notes(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    notes = request.form.get('notes', '')
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection error"}), 500
        cursor = conn.cursor()
        cursor.execute("UPDATE applicants SET admin_notes = %s, last_updated_at = NOW() WHERE applicant_id = %s", (notes, applicant_id))
        conn.commit()
        if cursor.rowcount > 0: return jsonify({"success": True, "message": f"Notes for P2025{applicant_id:04d} saved."})
        cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
        if cursor.fetchone()[0] > 0: return jsonify({"success": True, "message": "Notes saved (no change)."})
        return jsonify({"success": False, "message": "Application not found."}), 404
    except Exception as e:
        print(f"Error saving notes for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error saving notes."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/permit-details', methods=['POST'])
def admin_save_permit_details(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    data = {key: request.form.get(key) for key in ['permit_control_no', 'permit_exam_date', 'permit_exam_time', 'permit_testing_room']}
    permit_exam_date = None
    if data['permit_exam_date'] and data['permit_exam_date'].strip():
        try: permit_exam_date = datetime.datetime.strptime(data['permit_exam_date'], '%Y-%m-%d').date()
        except ValueError: return jsonify({"success": False, "message": "Invalid date format. Use YYYY-MM-DD."}), 400
    
    params = (
        data['permit_control_no'] or None, permit_exam_date,
        data['permit_exam_time'] or None, data['permit_testing_room'] or None, applicant_id
    )
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection error"}), 500
        cursor = conn.cursor()
        cursor.execute("UPDATE applicants SET permit_control_no=%s, permit_exam_date=%s, permit_exam_time=%s, permit_testing_room=%s, last_updated_at=NOW() WHERE applicant_id=%s", params)
        conn.commit()
        if cursor.rowcount > 0: return jsonify({"success": True, "message": f"Permit details for P2025{applicant_id:04d} saved."})
        cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
        if cursor.fetchone()[0] > 0: return jsonify({"success": True, "message": "Permit details saved (no change)."})
        return jsonify({"success": False, "message": "Application not found."}), 404
    except Exception as e:
        print(f"Error saving permit details for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error saving permit details."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/control-number', methods=['POST'])
def admin_save_control_number(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    control_number = request.form.get('control_number')
    control_number = control_number.strip() if control_number and control_number.strip() else None
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection error"}), 500
        cursor = conn.cursor()
        cursor.execute("UPDATE applicants SET control_number = %s, last_updated_at = NOW() WHERE applicant_id = %s", (control_number, applicant_id))
        conn.commit()
        if cursor.rowcount > 0: return jsonify({"success": True, "message": f"Control number for P2025{applicant_id:04d} saved."})
        cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
        if cursor.fetchone()[0] > 0: return jsonify({"success": True, "message": "Control number saved (no change)."})
        return jsonify({"success": False, "message": "Application not found."}), 404
    except Exception as e:
        print(f"Error saving control number for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error saving control number."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/create_application_by_admin', methods=['POST'])
def admin_add_application_by_admin_action():
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    if request.method != 'POST': return jsonify({"success": False, "message": "Invalid request method."}), 405

    conn = None; cursor = None
    MAX_PHOTO_SIZE_MB, MAX_DOC_SIZE_MB = 5, 5

    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection error."}), 500
        
        field_list = [
            'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth',
            'sex', 'civil_status', 'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability',
            'date_of_application', 'academic_year', 'average_family_income',
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number',
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number',
            'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number',
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand',
            'senior_high_school_year_from', 'senior_high_school_year_to',
            'tertiary_school', 'tertiary_school_address', 'tertiary_course',
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'final_submission_date'
        ]
        req_text_fields = [f for f in field_list if f not in ['middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to']]
        req_date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date']

        form_data = {}
        for field in field_list:
            val = request.form.get(field)
            if field in req_text_fields and (not val or not val.strip()): return jsonify({"success": False, "message": f"{field.replace('_',' ').title()} is required."}), 400
            if field in req_date_fields and not val: return jsonify({"success": False, "message": f"{field.replace('_',' ').title()} date is required."}), 400
            if field == 'agreements' and val != 'Yes': return jsonify({"success": False, "message": "Admin must confirm agreement."}), 400
            form_data[field] = val.strip() if val and isinstance(val, str) else val
        
        applicant_email = form_data.get('email_address')
        if not applicant_email: return jsonify({"success": False, "message": "Email is required."}), 400

        # Student User Account Handling
        student_user_cursor = conn.cursor(dictionary=True)
        student_user_cursor.execute("SELECT id FROM student_users WHERE email = %s", (applicant_email,))
        existing_user = student_user_cursor.fetchone()
        student_user_cursor.close()

        student_user_id, temp_pass, acc_msg = None, None, ""
        if existing_user:
            student_user_id = existing_user['id']
            acc_msg = f"Linked to existing student account (ID: {student_user_id})."
        else:
            temp_pass = secrets.token_urlsafe(10)
            hashed_pass = generate_password_hash(temp_pass, method='pbkdf2:sha256')
            insert_user_curs = conn.cursor()
            try:
                insert_user_curs.execute("INSERT INTO student_users (email, password, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())", (applicant_email, hashed_pass))
                conn.commit()
                student_user_id = insert_user_curs.lastrowid
                if not student_user_id: conn.rollback(); return jsonify({"success": False, "message": "Failed to create student account."}), 500
                acc_msg = f"New student account created (ID: {student_user_id})."
            except mysql.connector.Error as user_err:
                conn.rollback(); print(f"DB Error (User Create): {user_err}"); traceback.print_exc()
                return jsonify({"success": False, "message": f"DB error creating student account: {user_err}"}), 500
            finally:
                if insert_user_curs: insert_user_curs.close()
        
        # File Processing
        files_data = {}
        file_fields = {
            'photo': ('2x2 Photo', MAX_PHOTO_SIZE_MB), 
            'shs_diploma_file_input': ('SHS Diploma', MAX_DOC_SIZE_MB),
            'shs_card_file_input': ('SHS Card', MAX_DOC_SIZE_MB),
            'birth_certificate_file_input': ('Birth Certificate', MAX_DOC_SIZE_MB)
        }
        for form_key, (desc, max_size) in file_fields.items():
            file_store = request.files.get(form_key)
            if file_store and file_store.filename:
                data, fname, mtype, err = process_uploaded_file(file_store, desc, max_size)
                if err: return jsonify({"success": False, "message": f"{desc} Error: {err}"}), 400
                files_data[form_key] = {'data': data, 'filename': fname, 'mimetype': mtype}

        # Insert into applicants table
        db_cols = [
            'student_user_id', 'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth',
            'sex', 'civil_status', 'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'control_number', 
            'date_of_application', 'academic_year', 'average_family_income',
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number',
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number',
            'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number',
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand',
            'senior_high_school_year_from', 'senior_high_school_year_to',
            'tertiary_school', 'tertiary_school_address', 'tertiary_course',
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'final_submission_date',
            'photo', 'shs_diploma_file', 'shs_diploma_filename', 'shs_diploma_mimetype',
            'shs_card_file', 'shs_card_filename', 'shs_card_mimetype',
            'birth_certificate_file', 'birth_certificate_filename', 'birth_certificate_mimetype',
            'application_status', 'submitted_at', 'last_updated_at', 'exam_status'
        ]
        
        insert_vals = [student_user_id] + [form_data.get(col_name) for col_name in field_list if col_name in db_cols and col_name != 'student_user_id'] # Simplified based on `field_list`
        
        # Reconstruct insert_vals more carefully to match db_cols order
        final_insert_vals = []
        now = datetime.datetime.now()
        for col in db_cols:
            if col == 'student_user_id': final_insert_vals.append(student_user_id)
            elif col == 'control_number': final_insert_vals.append(None)
            elif col == 'photo': final_insert_vals.append(files_data.get('photo', {}).get('data'))
            elif col == 'shs_diploma_file': final_insert_vals.append(files_data.get('shs_diploma_file_input', {}).get('data'))
            elif col == 'shs_diploma_filename': final_insert_vals.append(files_data.get('shs_diploma_file_input', {}).get('filename'))
            elif col == 'shs_diploma_mimetype': final_insert_vals.append(files_data.get('shs_diploma_file_input', {}).get('mimetype'))
            elif col == 'shs_card_file': final_insert_vals.append(files_data.get('shs_card_file_input', {}).get('data'))
            elif col == 'shs_card_filename': final_insert_vals.append(files_data.get('shs_card_file_input', {}).get('filename'))
            elif col == 'shs_card_mimetype': final_insert_vals.append(files_data.get('shs_card_file_input', {}).get('mimetype'))
            elif col == 'birth_certificate_file': final_insert_vals.append(files_data.get('birth_certificate_file_input', {}).get('data'))
            elif col == 'birth_certificate_filename': final_insert_vals.append(files_data.get('birth_certificate_file_input', {}).get('filename'))
            elif col == 'birth_certificate_mimetype': final_insert_vals.append(files_data.get('birth_certificate_file_input', {}).get('mimetype'))
            elif col == 'application_status': final_insert_vals.append('Pending')
            elif col == 'submitted_at': final_insert_vals.append(now)
            elif col == 'last_updated_at': final_insert_vals.append(now)
            elif col == 'exam_status': final_insert_vals.append(None)
            elif col in form_data: final_insert_vals.append(form_data[col])
            else: final_insert_vals.append(None) # Should not happen if db_cols is exhaustive

        if len(final_insert_vals) != len(db_cols):
             return jsonify({"success": False, "message": f"Internal Error: Column count mismatch ({len(final_insert_vals)} vs {len(db_cols)})."}), 500

        cursor = conn.cursor()
        query = f"INSERT INTO applicants (`{ '`, `'.join(db_cols) }`) VALUES ({ ', '.join(['%s']*len(db_cols)) })"
        cursor.execute(query, tuple(final_insert_vals))
        conn.commit()
        
        email_notif_msg = ""
        if temp_pass and student_user_id:
            full_name = f"{form_data.get('first_name','')} {form_data.get('last_name','_')}".strip()
            email_sent = send_admin_created_account_email(applicant_email, full_name, temp_pass)
            email_notif_msg = " Account credentials email sent." if email_sent else " Failed to send credentials email."
        
        return jsonify({"success": True, "message": f"Application added. {acc_msg}{email_notif_msg}"})

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        print(f"DB Error (Admin Add App): {err}"); traceback.print_exc()
        return jsonify({"success": False, "message": f"Database Error: {err}"}), 500
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        print(f"Unexpected Error (Admin Add App): {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": f"Unexpected error: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin', methods=['GET'])
def admin():
    return render_template("admin.html")

@auth.route('/logout', methods=['GET'])
def logout():
    session.clear()
    flash("✅ You have been logged out.", "success")
    return redirect(url_for('views.home'))

@auth.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin')
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        flash("✅ Admin login successful!", "success")
        return redirect(url_for('auth.admin_dashboard'))
    else:
        flash('Invalid admin credentials', "danger")
        return redirect(url_for('auth.admin'))

@auth.route('/admin/application/<int:applicant_id>/print', methods=['GET'])
def admin_print_application_form(applicant_id):
    if not session.get('admin_logged_in'):
        flash("⚠️ Please log in to access this page.", "warning")
        return redirect(url_for('auth.admin'))
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: flash("Database connection error.", "danger"); return redirect(url_for('auth.admin_dashboard'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT a.*, su.email as student_account_email FROM applicants a LEFT JOIN student_users su ON a.student_user_id = su.id WHERE a.applicant_id = %s", (applicant_id,))
        app_data = cursor.fetchone()
        if not app_data: flash("Application not found.", "danger"); return redirect(url_for('auth.admin_dashboard'))

        application = app_data.copy()
        # Decode byte strings and format dates/photo
        string_fields = [
            'program_choice', 'last_name', 'first_name', 'middle_name', 'place_of_birth', 'sex', 'civil_status', 
            'religion', 'citizenship', 'mobile_number', 'email_address', 'permanent_address_street_barangay', 
            'permanent_address_city_municipality', 'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'average_family_income', 'father_name', 
            'father_occupation', 'father_company_address', 'father_contact_number', 'mother_maiden_name', 
            'mother_occupation', 'mother_company_address', 'mother_contact_number', 'guardian_name', 
            'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'senior_high_school', 
            'senior_high_school_address', 'senior_high_school_track_strand', 'senior_high_school_year_from', 
            'senior_high_school_year_to', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'academic_year', 'permit_control_no', 
            'permit_exam_time', 'permit_testing_room', 'control_number', 'application_status', 'exam_status', 'admin_notes'
        ]
        for key in string_fields:
            if key in application and isinstance(application[key], bytes):
                try: application[key] = application[key].decode('utf-8')
                except UnicodeDecodeError: application[key] = f"Undecodable ({len(application[key])} bytes)"
            elif key in application and application[key] is not None and not isinstance(application[key], (str, int, float, datetime.date, datetime.datetime)):
                 application[key] = str(application[key]) # For enums or other non-standard types

        if application.get('photo') and isinstance(application['photo'], bytes):
            fmt = "jpeg"
            if application['photo'].startswith(b'\x89PNG\r\n\x1a\n'): fmt = "png"
            application['photo_base64'] = f"data:image/{fmt};base64,{base64.b64encode(application['photo']).decode('utf-8')}"
        else: application['photo_base64'] = None

        date_fields_display = ['date_of_birth', 'date_of_application', 'final_submission_date', 'permit_exam_date']
        datetime_fields_display = ['submitted_at', 'decision_date', 'last_updated_at']
        for field in date_fields_display + datetime_fields_display:
            val = application.get(field)
            if isinstance(val, (datetime.datetime, datetime.date)):
                application[field + '_formatted'] = val.strftime('%B %d, %Y' if field in date_fields_display else '%Y-%m-%d %I:%M %p')
            elif val: application[field + '_formatted'] = str(val)
            else: application[field + '_formatted'] = 'N/A'
        
        # Ensure all expected fields for template have a default
        all_expected_for_template = string_fields + date_fields_display + datetime_fields_display
        for key in all_expected_for_template:
            application.setdefault(key, '')
            application.setdefault(key + '_formatted', 'N/A' if application[key] == '' else str(application[key]))

        return render_template('printable_application_form.html', application=application)
    except Exception as e:
        flash(f"Error printing application: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.admin_dashboard'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- STUDENT AUTHENTICATION ROUTES -----------------
@auth.route('/create-student-account', methods=['GET', 'POST'])
def create_student_account_page(): 
    if 'student_id' in session: return redirect(url_for('views.application_status_page'))
    if request.method == 'POST':
        email, password, confirm_password = request.form.get('email'), request.form.get('password'), request.form.get('confirm_password')
        if not all([email, password, confirm_password]): flash('Please fill out all fields.', 'warning'); return redirect(url_for('auth.create_student_account_page'))
        if password != confirm_password: flash('Passwords do not match.', 'danger'); return redirect(url_for('auth.create_student_account_page'))
        if len(password) < 8: flash('Password must be at least 8 characters long.', 'danger'); return redirect(url_for('auth.create_student_account_page'))
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        otp_code = f"{secrets.randbelow(1000000):06d}" # Generate 6-digit OTP
        otp_expiry = datetime.datetime.now() + timedelta(minutes=10) # OTP valid for 10 minutes

        conn = None; cursor = None
        try:
            conn = get_db_connection()
            if not conn: flash("Database error.", "danger"); return redirect(url_for('auth.create_student_account_page'))
            cursor = conn.cursor(dictionary=True) # Use dictionary cursor
            cursor.execute("SELECT email, is_verified FROM student_users WHERE email = %s", (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                if existing_user['is_verified']:
                    flash('Email already registered and verified. Please log in.', 'danger')
                    return redirect(url_for('auth.student_login_page'))
                else:
                    # User exists but not verified, update OTP, password and resend
                    cursor.execute("""
                        UPDATE student_users 
                        SET password = %s, otp_code = %s, otp_expiry = %s, updated_at = NOW()
                        WHERE email = %s
                    """, (hashed_password, otp_code, otp_expiry, email))
                    conn.commit()
                    email_sent = send_otp_email(email, otp_code)
                    if email_sent:
                        flash('Account existed but was not verified. A new OTP has been sent to your email. Please verify to continue.', 'info')
                    else:
                        flash('Failed to send OTP email. Please try again later.', 'danger')
                    session['pending_verification_email'] = email 
                    return redirect(url_for('auth.verify_otp_page'))
            
            # New user, insert with OTP details
            cursor.execute("""
                INSERT INTO student_users 
                (email, password, created_at, updated_at, otp_code, otp_expiry, is_verified) 
                VALUES (%s, %s, NOW(), NOW(), %s, %s, %s)
            """, (email, hashed_password, otp_code, otp_expiry, False))
            conn.commit()
            
            email_sent = send_otp_email(email, otp_code)
            if email_sent:
                flash('✅ Account created! Please check your email for an OTP to verify your account.', 'success')
            else:
                flash('Account created, but failed to send OTP email. Please try verifying later or contact support.', 'warning')
            
            session['pending_verification_email'] = email 
            return redirect(url_for('auth.verify_otp_page'))

        except mysql.connector.Error as db_err:
            if db_err.errno == 1062: 
                 flash('Email already registered. If not verified, try creating account again to resend OTP or try logging in.', 'danger')
            else:
                flash(f'Database error creating account: {db_err}', 'danger')
            traceback.print_exc()
            return redirect(url_for('auth.create_student_account_page'))
        except Exception as e:
            flash(f'Error creating account: {e}', 'danger'); traceback.print_exc()
            return redirect(url_for('auth.create_student_account_page'))
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    return render_template('create_account.html')

@auth.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp_page():
    email_to_verify = session.get('pending_verification_email')
    if not email_to_verify: # If email not in session, try getting from form (e.g. if user bookmarked or navigated directly)
        email_to_verify = request.form.get('email_for_verification') # Check form if it's a POST from verify_otp itself
        if not email_to_verify and request.args.get('email'): # Check query param for GET requests
            email_to_verify = request.args.get('email')
            session['pending_verification_email'] = email_to_verify # Re-set session
        elif not email_to_verify :
            flash("No email found for verification. Please start by creating an account or trying to log in.", "warning")
            return redirect(url_for('auth.create_student_account_page'))


    if request.method == 'POST':
        otp_entered = request.form.get('otp_code')
        # Ensure email_to_verify is consistently used, preferring session then form
        email_from_form = request.form.get('email_for_verification')
        if email_from_form and email_from_form != email_to_verify: # Should ideally not happen if session is solid
            email_to_verify = email_from_form
            session['pending_verification_email'] = email_to_verify

        if not otp_entered:
            flash("Please enter the OTP.", "warning")
            return render_template('verify_otp.html', email=email_to_verify)

        conn = None; cursor = None
        try:
            conn = get_db_connection()
            if not conn:
                flash("Database connection error.", "danger")
                return render_template('verify_otp.html', email=email_to_verify)
            
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, otp_code, otp_expiry, is_verified FROM student_users WHERE email = %s", (email_to_verify,))
            user = cursor.fetchone()

            if not user:
                flash("User not found. Please try creating an account again.", "danger")
                session.pop('pending_verification_email', None) 
                return redirect(url_for('auth.create_student_account_page'))
            
            if user['is_verified']:
                flash("Account already verified. You can log in.", "info")
                session.pop('pending_verification_email', None) 
                return redirect(url_for('auth.student_login_page'))

            db_otp_expiry = user['otp_expiry']
            if isinstance(db_otp_expiry, str): # Ensure it's datetime
                try: db_otp_expiry = datetime.datetime.fromisoformat(db_otp_expiry)
                except ValueError:
                    flash("OTP expiry data error. Contact support.", "danger")
                    return render_template('verify_otp.html', email=email_to_verify)
            
            if not user['otp_code'] or not db_otp_expiry :
                flash("OTP not set or issue with expiry for this account. Try resending OTP.", "danger")
                return render_template('verify_otp.html', email=email_to_verify, show_resend=True)


            if db_otp_expiry < datetime.datetime.now():
                flash("OTP has expired. Please request a new one.", "danger")
                return render_template('verify_otp.html', email=email_to_verify, show_resend=True)

            if user['otp_code'] == otp_entered:
                cursor.execute("""
                    UPDATE student_users 
                    SET is_verified = TRUE, otp_code = NULL, otp_expiry = NULL, updated_at = NOW()
                    WHERE id = %s
                """, (user['id'],))
                conn.commit()
                flash("✅ Account verified successfully! You can now log in.", "success")
                session.pop('pending_verification_email', None) 
                return redirect(url_for('auth.student_login_page'))
            else:
                flash("Invalid OTP. Please try again.", "danger")
                return render_template('verify_otp.html', email=email_to_verify)

        except Exception as e:
            flash(f"An error occurred during OTP verification: {e}", "danger")
            traceback.print_exc()
            return render_template('verify_otp.html', email=email_to_verify)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

    return render_template('verify_otp.html', email=email_to_verify)

@auth.route('/resend-otp', methods=['POST'])
def resend_otp_action():
    email_to_resend = request.form.get('email') 
    
    if not email_to_resend:
        flash("Email not provided for OTP resend.", "warning")
        email_to_resend = session.get('pending_verification_email')
        if not email_to_resend:
             return redirect(url_for('auth.create_student_account_page'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.verify_otp_page', email=email_to_resend))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, is_verified FROM student_users WHERE email = %s", (email_to_resend,))
        user = cursor.fetchone()

        if not user:
            flash(f"No account found for email {email_to_resend}. Please create an account.", "danger")
            session.pop('pending_verification_email', None)
            return redirect(url_for('auth.create_student_account_page'))

        if user['is_verified']:
            flash("Account is already verified. You can log in.", "info")
            session.pop('pending_verification_email', None)
            return redirect(url_for('auth.student_login_page'))

        new_otp_code = f"{secrets.randbelow(1000000):06d}"
        new_otp_expiry = datetime.datetime.now() + timedelta(minutes=10)

        cursor.execute("""
            UPDATE student_users 
            SET otp_code = %s, otp_expiry = %s, updated_at = NOW()
            WHERE id = %s
        """, (new_otp_code, new_otp_expiry, user['id']))
        conn.commit()

        email_sent = send_otp_email(email_to_resend, new_otp_code)
        if email_sent:
            flash("A new OTP has been sent to your email address.", "success")
        else:
            flash("Failed to send new OTP. Please try again later or contact support.", "danger")
        
        session['pending_verification_email'] = email_to_resend 
        return redirect(url_for('auth.verify_otp_page')) # Redirect without email in query, relies on session

    except Exception as e:
        flash(f"Error resending OTP: {e}", "danger")
        traceback.print_exc()
        if email_to_resend:
            session['pending_verification_email'] = email_to_resend
        return redirect(url_for('auth.verify_otp_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/student-login', methods=['GET', 'POST'])
def student_login_page(): 
    if 'student_id' in session: return redirect(url_for('views.application_status_page'))
    if request.method == 'POST':
        email, password = request.form.get('email'), request.form.get('password')
        if not email or not password: flash('Please fill out all fields.', 'warning'); return redirect(url_for('auth.student_login_page'))
        conn = None; cursor = None
        try:
            conn = get_db_connection()
            if not conn: flash("Database error.", "danger"); return redirect(url_for('auth.student_login_page'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, email, password, is_verified FROM student_users WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user:
                if not user['is_verified']:
                    flash('Your account is not verified. Please check your email for an OTP or request a new one on the verification page.', 'warning')
                    session['pending_verification_email'] = email 
                    return redirect(url_for('auth.verify_otp_page')) 

                if check_password_hash(user['password'], password):
                    session['student_id'] = user['id']
                    session['student_email'] = user['email']
                    flash('✅ Login successful!', 'success')
                    session.pop('pending_verification_email', None) 
                    return redirect(url_for('views.application_status_page'))
                else:
                    flash('Invalid email or password.', 'danger')
                    return redirect(url_for('auth.student_login_page'))
            else:
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('auth.student_login_page'))
        except Exception as e:
            flash(f'Login error: {e}', 'danger'); traceback.print_exc()
            return redirect(url_for('auth.student_login_page'))
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    return render_template('student_login.html')

# ----------------- STUDENT FORGOT/RESET PASSWORD ROUTES -----------------
@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password_request_page(): 
    if request.method == 'POST':
        email = request.form.get('email')
        if not email: flash("Please enter your email.", "warning"); return redirect(url_for('auth.forgot_password_request_page'))
        conn = None; cursor = None
        try:
            conn = get_db_connection()
            if not conn: flash("Database error.", "danger"); return redirect(url_for('auth.forgot_password_request_page'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM student_users WHERE email = %s", (email,))
            user = cursor.fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                expiry = datetime.datetime.now() + timedelta(hours=1)
                cursor.execute("UPDATE student_users SET reset_token = %s, reset_token_expiry = %s WHERE id = %s", (token, expiry, user['id']))
                conn.commit()
                email_sent, reset_url = send_password_reset_email(email, token)
                if email_sent: flash(f"Password reset link sent to {email}.", "success")
                else: flash("Error sending email. Try again later.", "danger"); print(f"Failed reset email to {email}. Link: {reset_url}")
            else:
                flash(f"Email '{email}' not registered.", "danger")
            return redirect(url_for('auth.forgot_password_request_page'))
        except Exception as e:
            flash(f'Error processing request: {e}', 'danger'); traceback.print_exc()
            return redirect(url_for('auth.forgot_password_request_page'))
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    return render_template('forgot_password_request.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_page(token): 
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: flash("Database error.", "danger"); return redirect(url_for('auth.forgot_password_request_page'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, reset_token_expiry FROM student_users WHERE reset_token = %s", (token,))
        user = cursor.fetchone()

        if not user: flash("Invalid token.", "danger"); return redirect(url_for('auth.forgot_password_request_page'))
        
        expiry_time = user.get('reset_token_expiry')
        # Ensure expiry_time is datetime object before comparison
        if isinstance(expiry_time, str): # Or other non-datetime types from DB
            try: expiry_time = datetime.datetime.fromisoformat(expiry_time) # Or appropriate parsing
            except ValueError: 
                flash("Token expiry format error.", "danger"); return redirect(url_for('auth.forgot_password_request_page'))

        if not expiry_time or expiry_time < datetime.datetime.now():
            flash("Token expired.", "danger")
            cursor.execute("UPDATE student_users SET reset_token = NULL, reset_token_expiry = NULL WHERE id = %s", (user['id'],))
            conn.commit()
            return redirect(url_for('auth.forgot_password_request_page'))

        if request.method == 'POST':
            password, confirm_pass = request.form.get('password'), request.form.get('confirm_password')
            if not all([password, confirm_pass]): flash("Fill all fields.", "warning"); return render_template('reset_password_form.html', token=token)
            if password != confirm_pass: flash("Passwords don't match.", "danger"); return render_template('reset_password_form.html', token=token)
            if len(password) < 8: flash('Password too short.', 'danger'); return render_template('reset_password_form.html', token=token)
            
            hashed_pass = generate_password_hash(password, method='pbkdf2:sha256')
            cursor.execute("UPDATE student_users SET password = %s, reset_token = NULL, reset_token_expiry = NULL, updated_at = NOW() WHERE id = %s", (hashed_pass, user['id']))
            conn.commit()
            flash('✅ Password reset! Please log in.', 'success')
            return redirect(url_for('auth.student_login_page'))
        
        return render_template('reset_password_form.html', token=token)

    except Exception as e:
        flash(f'Error resetting password: {e}', 'danger'); traceback.print_exc()
        return redirect(url_for('auth.forgot_password_request_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# ----------------- APPLICATION FORM SUBMISSION (NEW STUDENT) -----------------
@auth.route('/submit_application', methods=['POST'])
def submit_application():
    if 'student_id' not in session: flash("⚠️ Log in to submit.", "warning"); return redirect(url_for('auth.student_login_page'))
    if request.method != 'POST': return redirect(url_for('views.new_student'))

    conn = None; cursor = None
    student_user_id = session['student_id']
    MAX_PHOTO_SIZE_MB, MAX_DOC_SIZE_MB = 5, 5

    try:
        # File uploads first
        files_to_upload = {
            'photo': ('2x2 Photo', MAX_PHOTO_SIZE_MB, True), 
            'shs_diploma_file_input': ('SHS Diploma', MAX_DOC_SIZE_MB, True),
            'shs_card_file_input': ('SHS Card', MAX_DOC_SIZE_MB, True),
            'birth_certificate_file_input': ('Birth Certificate', MAX_DOC_SIZE_MB, True)
        }
        processed_files = {}
        for key, (desc, max_size, is_required) in files_to_upload.items():
            file_storage = request.files.get(key)
            data, fname, mtype, err = process_uploaded_file(file_storage, desc, max_size)
            if err: flash(f"⚠️ {err}", "danger"); return redirect(url_for('views.new_student'))
            if is_required and not data: flash(f"⚠️ {desc} is required.", "danger"); return redirect(url_for('views.new_student'))
            if data: processed_files[key] = {'data': data, 'filename': fname, 'mimetype': mtype}

        # Form fields
        field_list = [
            'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth',
            'sex', 'civil_status', 'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability',
            'date_of_application', 'academic_year', 'average_family_income',
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number',
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number',
            'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number',
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand',
            'senior_high_school_year_from', 'senior_high_school_year_to',
            'tertiary_school', 'tertiary_school_address', 'tertiary_course',
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'final_submission_date'
        ]
        req_text_fields = [f for f in field_list if f not in ['middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to']]
        req_date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date']
        
        form_data = {}
        for field in field_list:
            val = request.form.get(field)
            if field in req_text_fields and (not val or not val.strip()): flash(f"⚠️ {field.replace('_',' ').title()} is required.", "danger"); return redirect(url_for('views.new_student'))
            if field in req_date_fields and not val: flash(f"⚠️ {field.replace('_',' ').title()} date required.", "danger"); return redirect(url_for('views.new_student'))
            if field == 'agreements' and val != 'Yes': flash("⚠️ Agree to terms.", "danger"); return redirect(url_for('views.new_student'))
            form_data[field] = val.strip() if val and isinstance(val, str) else val

        conn = get_db_connection();
        if not conn: flash("Database error.", "danger"); return redirect(url_for('views.new_student'))
        cursor = conn.cursor()
        cursor.execute("SELECT applicant_id FROM applicants WHERE student_user_id = %s AND application_status IN ('Pending', 'In Review', 'Approved', 'Passed')", (student_user_id,))
        if cursor.fetchone(): flash("⚠️ Active/Approved/Passed application exists.", "warning"); return redirect(url_for('views.application_status_page'))

        db_cols_app_insert = [
            'student_user_id', 'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth', 'sex', 'civil_status', 
            'religion', 'citizenship', 'mobile_number', 'email_address', 'permanent_address_street_barangay', 
            'permanent_address_city_municipality', 'permanent_address_province', 'permanent_address_postal_code', 
            'cultural_minority_group', 'physical_disability', 'control_number', 'date_of_application', 'academic_year', 
            'average_family_income', 'father_name', 'father_occupation', 'father_company_address', 'father_contact_number', 
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number', 'guardian_name', 
            'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'senior_high_school', 
            'senior_high_school_address', 'senior_high_school_track_strand', 'senior_high_school_year_from', 
            'senior_high_school_year_to', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'final_submission_date', 'photo', 
            'shs_diploma_file', 'shs_diploma_filename', 'shs_diploma_mimetype', 'shs_card_file', 'shs_card_filename', 
            'shs_card_mimetype', 'birth_certificate_file', 'birth_certificate_filename', 'birth_certificate_mimetype', 
            'application_status', 'submitted_at', 'last_updated_at', 'exam_status'
        ]
        now = datetime.datetime.now()
        app_insert_vals = [
            student_user_id, form_data.get('program_choice'), form_data.get('last_name'), form_data.get('first_name'), form_data.get('middle_name'),
            form_data.get('date_of_birth'), form_data.get('place_of_birth'), form_data.get('sex'), form_data.get('civil_status'),
            form_data.get('religion'), form_data.get('citizenship'), form_data.get('mobile_number'), form_data.get('email_address'),
            form_data.get('permanent_address_street_barangay'), form_data.get('permanent_address_city_municipality'),
            form_data.get('permanent_address_province'), form_data.get('permanent_address_postal_code'),
            form_data.get('cultural_minority_group'), form_data.get('physical_disability'), None, # control_number
            form_data.get('date_of_application'), form_data.get('academic_year'), form_data.get('average_family_income'),
            form_data.get('father_name'), form_data.get('father_occupation'), form_data.get('father_company_address'), form_data.get('father_contact_number'),
            form_data.get('mother_maiden_name'), form_data.get('mother_occupation'), form_data.get('mother_company_address'), form_data.get('mother_contact_number'),
            form_data.get('guardian_name'), form_data.get('guardian_occupation'), form_data.get('guardian_company_address'), form_data.get('guardian_contact_number'),
            form_data.get('senior_high_school'), form_data.get('senior_high_school_address'), form_data.get('senior_high_school_track_strand'),
            form_data.get('senior_high_school_year_from'), form_data.get('senior_high_school_year_to'),
            form_data.get('tertiary_school'), form_data.get('tertiary_school_address'), form_data.get('tertiary_course'),
            form_data.get('tertiary_year_from'), form_data.get('tertiary_year_to'),
            form_data.get('agreements'), form_data.get('final_submission_date'),
            processed_files.get('photo', {}).get('data'),
            processed_files.get('shs_diploma_file_input', {}).get('data'), processed_files.get('shs_diploma_file_input', {}).get('filename'), processed_files.get('shs_diploma_file_input', {}).get('mimetype'),
            processed_files.get('shs_card_file_input', {}).get('data'), processed_files.get('shs_card_file_input', {}).get('filename'), processed_files.get('shs_card_file_input', {}).get('mimetype'),
            processed_files.get('birth_certificate_file_input', {}).get('data'), processed_files.get('birth_certificate_file_input', {}).get('filename'), processed_files.get('birth_certificate_file_input', {}).get('mimetype'),
            'Pending', now, now, None # application_status, submitted_at, last_updated_at, exam_status
        ]
        
        if len(app_insert_vals) != len(db_cols_app_insert):
            flash(f"Internal error: Mismatch {len(app_insert_vals)} vs {len(db_cols_app_insert)}.", "danger"); return redirect(url_for('views.new_student'))

        query = f"INSERT INTO applicants (`{ '`, `'.join(db_cols_app_insert) }`) VALUES ({ ', '.join(['%s']*len(db_cols_app_insert)) })"
        cursor.execute(query, tuple(app_insert_vals))
        conn.commit()
        flash("✅ Application submitted! Check status now.", "success")
        return redirect(url_for('views.application_status_page'))

    except Exception as e:
        flash(f"⚠️ Error submitting: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('views.new_student'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# ----------------- ADMIN APPLICATION MANAGEMENT API ROUTES -----------------
@auth.route('/admin/application/<int:applicant_id>/status', methods=['POST'])
def admin_update_application_status(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    new_status = request.form.get('status')
    valid_statuses = ['Pending', 'In Review', 'Approved', 'Rejected', 'Passed', 'Failed']
    if not new_status or new_status not in valid_statuses: return jsonify({"success": False, "message": "Invalid status"}), 400

    conn = None; app_info_cursor = None; update_cursor = None; check_cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "DB error"}), 500
        
        app_info_cursor = conn.cursor(dictionary=True)
        app_info_cursor.execute("SELECT a.first_name, a.last_name, a.program_choice, a.exam_status, su.email as student_account_email, a.email_address as application_form_email FROM applicants a LEFT JOIN student_users su ON a.student_user_id = su.id WHERE a.applicant_id = %s", (applicant_id,))
        app_info = app_info_cursor.fetchone()
        if not app_info: return jsonify({"success": False, "message": "App not found"}), 404

        email_to_notify = app_info.get('student_account_email') or app_info.get('application_form_email')
        applicant_name = f"{app_info.get('first_name','')} {app_info.get('last_name','')}".strip()
        now = datetime.datetime.now()
        
        update_cursor = conn.cursor()
        sql = "UPDATE applicants SET application_status = %s, last_updated_at = %s"
        params = [new_status, now]
        if new_status in ['Approved', 'Rejected', 'Passed', 'Failed']:
            sql += ", decision_date = %s"
            params.append(now)
        else:
            sql += ", decision_date = NULL"
        sql += " WHERE applicant_id = %s"
        params.append(applicant_id)
        update_cursor.execute(sql, tuple(params))
        conn.commit()

        if update_cursor.rowcount > 0:
            email_sent = False
            if new_status in ['Approved', 'Rejected', 'Passed', 'Failed'] and email_to_notify:
                email_sent = send_application_status_email(email_to_notify, applicant_name, new_status, applicant_id, app_info.get('program_choice'), app_info.get('exam_status'))
            
            msg = f"P2025{applicant_id:04d} status to {new_status}."
            if new_status in ['Approved', 'Rejected', 'Passed', 'Failed'] and email_to_notify:
                msg += " Email sent." if email_sent else " Email failed."
            return jsonify({"success": True, "message": msg, "new_status": new_status, "applicant_id": applicant_id})
        else:
            check_cursor = conn.cursor()
            check_cursor.execute("SELECT 1 FROM applicants WHERE applicant_id = %s", (applicant_id,))
            if check_cursor.fetchone(): return jsonify({"success": True, "message": f"Status already {new_status}.", "new_status": new_status, "applicant_id": applicant_id})
            return jsonify({"success": False, "message": "App not found"}), 404
    except Exception as e:
        print(f"Error updating status for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error"}), 500
    finally:
        if app_info_cursor: app_info_cursor.close()
        if update_cursor: update_cursor.close()
        if check_cursor: check_cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/admin/application/<int:applicant_id>/exam-status', methods=['POST'])
def admin_update_exam_status(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    new_exam_status = request.form.get('exam_status')
    valid_exam_statuses = ['Passed', 'Failed', 'Not Taken', None, "null", ""]
    if new_exam_status not in valid_exam_statuses: return jsonify({"success": False, "message": "Invalid exam status."}), 400
    if new_exam_status in ["null", ""]: new_exam_status = None

    conn = None; cursor = None; app_info_cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "DB error"}), 500

        app_info_cursor = conn.cursor(dictionary=True)
        app_info_cursor.execute("SELECT a.first_name, a.last_name, a.program_choice, a.application_status, su.email as student_account_email, a.email_address as application_form_email FROM applicants a LEFT JOIN student_users su ON a.student_user_id = su.id WHERE a.applicant_id = %s", (applicant_id,))
        app_info = app_info_cursor.fetchone()
        if not app_info: return jsonify({"success": False, "message": "App not found."}), 404
        
        cursor = conn.cursor()
        cursor.execute("UPDATE applicants SET exam_status = %s, last_updated_at = NOW() WHERE applicant_id = %s", (new_exam_status, applicant_id))
        conn.commit()

        if cursor.rowcount > 0:
            email_to_notify = app_info.get('student_account_email') or app_info.get('application_form_email')
            applicant_name = f"{app_info.get('first_name','')} {app_info.get('last_name','')}".strip()
            email_sent = False
            if new_exam_status in ['Passed', 'Failed'] and email_to_notify and app_info.get('application_status') not in ['Approved', 'Rejected', 'Passed', 'Failed']:
                email_sent = send_application_status_email(email_to_notify, applicant_name, app_info.get('application_status'), applicant_id, app_info.get('program_choice'), new_exam_status)
            
            msg = f"Exam status for P2025{applicant_id:04d} to '{new_exam_status or 'Not Set'}'."
            if new_exam_status in ['Passed', 'Failed'] and email_to_notify and app_info.get('application_status') not in ['Approved', 'Rejected', 'Passed', 'Failed']:
                 msg += " Email sent." if email_sent else " Email failed."
            return jsonify({"success": True, "message": msg, "new_exam_status": new_exam_status, "applicant_id": applicant_id})
        else:
            cursor.execute("SELECT exam_status FROM applicants WHERE applicant_id = %s", (applicant_id,))
            db_status = cursor.fetchone()
            if db_status and db_status[0] == new_exam_status: return jsonify({"success": True, "message": f"Exam status already '{new_exam_status or 'Not Set'}'." , "new_exam_status": new_exam_status, "applicant_id": applicant_id})
            return jsonify({"success": False, "message": "App not found or status not updated."}), 404
    except Exception as e:
        print(f"Error updating exam status for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error"}), 500
    finally:
        if app_info_cursor: app_info_cursor.close()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/delete', methods=['POST'])
def admin_delete_application(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "DB error"}), 500
        cursor = conn.cursor()
        cursor.execute("DELETE FROM applicants WHERE applicant_id = %s", (applicant_id,))
        conn.commit()
        if cursor.rowcount > 0: return jsonify({"success": True, "message": f"P2025{applicant_id:04d} deleted."})
        return jsonify({"success": False, "message": "App not found"}), 404
    except Exception as e:
        print(f"Error deleting {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error deleting."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/details', methods=['GET'])
def admin_get_application_details(applicant_id):
    if not session.get('admin_logged_in'): return jsonify({"success": False, "message": "Unauthorized"}), 401
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "DB error"}), 500
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT a.*, su.email as student_account_email FROM applicants a LEFT JOIN student_users su ON a.student_user_id = su.id WHERE a.applicant_id = %s", (applicant_id,))
        app_data = cursor.fetchone()
        if app_data:
            for key, value in app_data.items():
                if isinstance(value, (datetime.datetime, datetime.date)): app_data[key] = value.isoformat()
                elif key == 'photo' and isinstance(value, bytes):
                    fmt = "jpeg"
                    if value.startswith(b'\x89PNG\r\n\x1a\n'): fmt = "png"
                    app_data[key] = f"data:image/{fmt};base64,{base64.b64encode(value).decode('utf-8')}" if value else None
                elif key in ['shs_diploma_file', 'shs_card_file', 'birth_certificate_file'] and isinstance(value, bytes):
                    app_data[key] = f"File data ({len(value)} bytes)" if value else None
                elif isinstance(value, bytes): 
                    try: app_data[key] = value.decode('utf-8')
                    except UnicodeDecodeError: app_data[key] = f"Binary ({len(value)} bytes)"
            return jsonify({"success": True, "data": app_data})
        return jsonify({"success": False, "message": "App not found"}), 404
    except Exception as e:
        print(f"Error fetching details for {applicant_id}: {e}"); traceback.print_exc()
        return jsonify({"success": False, "message": "Server error"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if not session.get('admin_logged_in'): flash("⚠️ Log in for admin dashboard.", "warning"); return redirect(url_for('auth.admin'))
    applications = []
    stats = {'total_applications': 0, 'pending': 0, 'in_review': 0, 'approved': 0, 'rejected': 0, 'passed': 0, 'failed': 0, 'passed_exam': 0, 'failed_exam': 0}
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT a.applicant_id, a.first_name, a.last_name, a.email_address, a.program_choice, a.date_of_application, a.application_status, a.submitted_at, a.decision_date, a.exam_status, su.email as student_account_email FROM applicants a LEFT JOIN student_users su ON a.student_user_id = su.id ORDER BY CASE a.application_status WHEN 'Pending' THEN 1 WHEN 'In Review' THEN 2 WHEN 'Approved' THEN 3 WHEN 'Passed' THEN 4 WHEN 'Failed' THEN 5 WHEN 'Rejected' THEN 6 ELSE 7 END, a.submitted_at DESC, a.applicant_id DESC")
            applications = cursor.fetchall()
            stats['total_applications'] = len(applications)
            for app in applications:
                for key, value in app.items(): # Decode bytes
                    if isinstance(value, bytes):
                        try: app[key] = value.decode('utf-8')
                        except UnicodeDecodeError: app[key] = "Decode Error"
                
                status_key = app.get('application_status','').lower().replace(' ', '_')
                if status_key in stats: stats[status_key] += 1
                if app.get('exam_status') == 'Passed': stats['passed_exam'] += 1
                elif app.get('exam_status') == 'Failed': stats['failed_exam'] += 1
        else: flash("Database error.", "danger")
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger"); traceback.print_exc()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return render_template('admin_dashboard.html', applications=applications, stats=stats)

# ----------------- DOCUMENT/PHOTO DOWNLOAD ROUTES -----------------
@auth.route('/applicant-photo/<int:applicant_id>')
def get_applicant_photo(applicant_id):
    is_admin = session.get('admin_logged_in', False)
    student_user_id = session.get('student_id', None)
    if not is_admin and not student_user_id: return "Unauthorized", 401

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: return "DB error", 500
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT photo, student_user_id FROM applicants WHERE applicant_id = %s", (applicant_id,))
        app_data = cursor.fetchone()
        if not app_data: return "Not found", 404
        if not is_admin and app_data.get('student_user_id') != student_user_id: return "Forbidden", 403
        if app_data.get('photo'):
            fmt = 'image/jpeg'
            if app_data['photo'].startswith(b'\x89PNG\r\n\x1a\n'): fmt = 'image/png'
            return Response(app_data['photo'], mimetype=fmt)
        return "No photo", 404
    except Exception as e:
        print(f"Error fetching photo for {applicant_id}: {e}"); traceback.print_exc()
        return "Server error", 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/applicant-document/<int:applicant_id>/<doc_type>')
def get_applicant_document(applicant_id, doc_type):
    is_admin = session.get('admin_logged_in', False)
    student_user_id = session.get('student_id', None)
    if not is_admin and not student_user_id: flash("Unauthorized.", "danger"); return redirect(request.referrer or url_for('views.home'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: flash("DB error.", "danger"); return redirect(request.referrer or url_for('views.home'))
        cursor = conn.cursor(dictionary=True)
        
        doc_map = {
            'diploma': ('shs_diploma_file', 'shs_diploma_filename', 'shs_diploma_mimetype'),
            'card': ('shs_card_file', 'shs_card_filename', 'shs_card_mimetype'),
            'birth_cert': ('birth_certificate_file', 'birth_certificate_filename', 'birth_certificate_mimetype')
        }
        if doc_type not in doc_map: flash("Invalid doc type.", "danger"); return redirect(request.referrer or url_for('views.home'))
        
        file_col, name_col, mime_col = doc_map[doc_type]
        cursor.execute(f"SELECT student_user_id, `{file_col}`, `{name_col}`, `{mime_col}` FROM applicants WHERE applicant_id = %s", (applicant_id,))
        app_data = cursor.fetchone()

        if not app_data: flash("App not found.", "danger"); return redirect(request.referrer or url_for('views.home'))
        if not is_admin and app_data.get('student_user_id') != student_user_id: flash("Forbidden.", "danger"); return redirect(request.referrer or url_for('views.home'))

        content, filename, mimetype = app_data.get(file_col), app_data.get(name_col), app_data.get(mime_col)
        if content and filename and mimetype:
            return send_file(io.BytesIO(content), mimetype=mimetype, as_attachment=True, download_name=filename)
        flash(f"{doc_type.title()} not found.", "warning"); return redirect(request.referrer or url_for('views.home'))
    except Exception as e:
        print(f"Error getting doc {doc_type} for {applicant_id}: {e}"); traceback.print_exc()
        flash("Server error retrieving document.", "danger"); return redirect(request.referrer or url_for('views.home'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# ----------------- STUDENT APPLICATION EDIT ROUTES -----------------
@auth.route('/edit-application/<int:applicant_id>', methods=['GET'])
def edit_application_page(applicant_id):
    if 'student_id' not in session: flash("⚠️ Log in to edit.", "warning"); return redirect(url_for('auth.student_login_page'))
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: flash("DB error.", "danger"); return redirect(url_for('views.application_status_page'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM applicants WHERE applicant_id = %s AND student_user_id = %s", (applicant_id, session['student_id']))
        application = cursor.fetchone()
        if not application: flash("App not found or no permission.", "danger"); return redirect(url_for('views.application_status_page'))
        if application['application_status'] not in ['Pending', 'In Review']: flash(f"App status '{application['application_status']}' not editable.", "warning"); return redirect(url_for('views.application_status_page'))

        processed_app = application.copy()
        date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date', 'permit_exam_date', 'submitted_at', 'decision_date', 'last_updated_at']
        date_input_fields = ['date_of_birth', 'date_of_application', 'final_submission_date', 'permit_exam_date']
        for field in date_fields:
            if field in processed_app and isinstance(processed_app[field], (datetime.datetime, datetime.date)):
                processed_app[field] = processed_app[field].strftime('%Y-%m-%d') if field in date_input_fields else processed_app[field].isoformat()
            elif field in date_input_fields and processed_app.get(field) is None: # ensure empty string for date inputs
                processed_app[field] = ""

        return render_template('edit_application.html', application=processed_app, student_logged_in=True)
    except Exception as e:
        flash(f"Error loading edit page: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('views.application_status_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/update-application/<int:applicant_id>', methods=['POST'])
def update_application_action(applicant_id):
    if 'student_id' not in session: flash("⚠️ Log in to update.", "warning"); return redirect(url_for('auth.student_login_page'))
    conn = None; cursor_check = None; cursor = None
    student_user_id = session['student_id']
    MAX_PHOTO_SIZE_MB, MAX_DOC_SIZE_MB = 5, 5

    try:
        conn = get_db_connection()
        if not conn: flash("DB error.", "danger"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
        
        cursor_check = conn.cursor(dictionary=True)
        cursor_check.execute("SELECT student_user_id, application_status FROM applicants WHERE applicant_id = %s", (applicant_id,))
        app_to_edit = cursor_check.fetchone()
        if not app_to_edit: flash("App not found.", "danger"); return redirect(url_for('views.application_status_page'))
        if app_to_edit['student_user_id'] != student_user_id: flash("No permission.", "danger"); return redirect(url_for('views.application_status_page'))
        if app_to_edit['application_status'] not in ['Pending', 'In Review']: flash(f"App status '{app_to_edit['application_status']}' not editable.", "warning"); return redirect(url_for('views.application_status_page'))
        
        field_list_update = [
            'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth', 'sex', 'civil_status',
            'religion', 'citizenship', 'mobile_number', 'email_address', 'permanent_address_street_barangay',
            'permanent_address_city_municipality', 'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'date_of_application', 'academic_year', 'average_family_income',
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number', 'mother_maiden_name',
            'mother_occupation', 'mother_company_address', 'mother_contact_number', 'guardian_name', 'guardian_occupation',
            'guardian_company_address', 'guardian_contact_number', 'senior_high_school', 'senior_high_school_address',
            'senior_high_school_track_strand', 'senior_high_school_year_from', 'senior_high_school_year_to',
            'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to',
            'agreements', 'final_submission_date'
        ]
        req_text_fields_edit = [f for f in field_list_update if f not in ['middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to']]
        req_date_fields_edit = ['date_of_birth', 'date_of_application', 'final_submission_date']

        update_clauses, values_for_update = [], []
        for field in field_list_update:
            val = request.form.get(field)
            if field in req_text_fields_edit and (not val or not val.strip()): flash(f"⚠️ {field.replace('_',' ').title()} required.", "danger"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
            if field in req_date_fields_edit and not val: flash(f"⚠️ {field.replace('_',' ').title()} date required.", "danger"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
            if field == 'agreements' and val != 'Yes': flash("⚠️ Re-agree to terms.", "danger"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
            processed_val = val.strip() if val and isinstance(val, str) else val
            update_clauses.append(f"`{field}` = %s"); values_for_update.append(processed_val)
        
        file_fields_to_check = {
            'photo': ('2x2 Photo', MAX_PHOTO_SIZE_MB), 
            'shs_diploma_file_input': ('SHS Diploma', MAX_DOC_SIZE_MB),
            'shs_card_file_input': ('SHS Card', MAX_DOC_SIZE_MB),
            'birth_certificate_file_input': ('Birth Certificate', MAX_DOC_SIZE_MB)
        }
        db_file_map = {
            'photo': ['photo'], 
            'shs_diploma_file_input': ['shs_diploma_file', 'shs_diploma_filename', 'shs_diploma_mimetype'],
            'shs_card_file_input': ['shs_card_file', 'shs_card_filename', 'shs_card_mimetype'],
            'birth_certificate_file_input': ['birth_certificate_file', 'birth_certificate_filename', 'birth_certificate_mimetype']
        }

        for form_key, (desc, max_size) in file_fields_to_check.items():
            file_storage = request.files.get(form_key)
            if file_storage and file_storage.filename:
                data, fname, mtype, err = process_uploaded_file(file_storage, desc, max_size)
                if err: flash(f"⚠️ {desc} Error: {err}", "danger"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
                if data:
                    if form_key == 'photo':
                        update_clauses.append("`photo` = %s"); values_for_update.append(data)
                    else:
                        update_clauses.extend([f"`{db_col}` = %s" for db_col in db_file_map[form_key]])
                        values_for_update.extend([data, fname, mtype])

        if not update_clauses: flash("No changes to update.", "info"); return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
        update_clauses.append("`last_updated_at` = %s"); values_for_update.append(datetime.datetime.now())
        
        query = f"UPDATE applicants SET {', '.join(update_clauses)} WHERE applicant_id = %s AND student_user_id = %s"
        values_for_update.extend([applicant_id, student_user_id])

        cursor = conn.cursor()
        cursor.execute(query, tuple(values_for_update))
        conn.commit()
        flash("✅ App updated!" if cursor.rowcount > 0 else "No changes made.", "success" if cursor.rowcount > 0 else "info")
        return redirect(url_for('views.application_status_page'))

    except Exception as e:
        flash(f"⚠️ Update Error: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
    finally:
        if cursor_check: cursor_check.close()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- ADMIN APPLICATION EDIT ROUTES (NEW) -----------------
@auth.route('/admin/edit-application/<int:applicant_id>', methods=['GET'])
def admin_edit_application_page(applicant_id):
    if not session.get('admin_logged_in'): flash("⚠️ Log in for admin edit.", "warning"); return redirect(url_for('auth.admin'))
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: flash("DB error.", "danger"); return redirect(url_for('auth.admin_dashboard'))
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM applicants WHERE applicant_id = %s", (applicant_id,))
        application = cursor.fetchone()
        if not application: flash("App not found.", "danger"); return redirect(url_for('auth.admin_dashboard'))
        
        processed_app = application.copy()
        date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date', 'permit_exam_date', 'submitted_at', 'decision_date', 'last_updated_at']
        date_input_fields = ['date_of_birth', 'date_of_application', 'final_submission_date', 'permit_exam_date']
        for field in date_fields:
            if field in processed_app and isinstance(processed_app[field], (datetime.datetime, datetime.date)):
                processed_app[field] = processed_app[field].strftime('%Y-%m-%d') if field in date_input_fields else processed_app[field].isoformat()
            elif field in date_input_fields and processed_app.get(field) is None: processed_app[field] = ""

        return render_template('admin_edit_application.html', application=processed_app, admin_logged_in=True)
    except Exception as e:
        flash(f"Error loading admin edit: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.admin_dashboard'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/update-application/<int:applicant_id>', methods=['POST'])
def admin_update_application_action(applicant_id):
    if not session.get('admin_logged_in'): flash("⚠️ Unauthorized.", "danger"); return redirect(url_for('auth.admin'))
    conn = None; cursor_check = None; cursor = None
    MAX_PHOTO_SIZE_MB, MAX_DOC_SIZE_MB = 5, 5

    try:
        conn = get_db_connection()
        if not conn: flash("DB error.", "danger"); return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
        cursor_check = conn.cursor(dictionary=True)
        cursor_check.execute("SELECT applicant_id FROM applicants WHERE applicant_id = %s", (applicant_id,))
        if not cursor_check.fetchone(): flash("App not found.", "danger"); return redirect(url_for('auth.admin_dashboard'))
        
        field_list_update_admin = [
            'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth', 'sex', 'civil_status',
            'religion', 'citizenship', 'mobile_number', 'email_address', 'permanent_address_street_barangay',
            'permanent_address_city_municipality', 'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'date_of_application', 'academic_year', 'average_family_income',
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number', 'mother_maiden_name',
            'mother_occupation', 'mother_company_address', 'mother_contact_number', 'guardian_name', 'guardian_occupation',
            'guardian_company_address', 'guardian_contact_number', 'senior_high_school', 'senior_high_school_address',
            'senior_high_school_track_strand', 'senior_high_school_year_from', 'senior_high_school_year_to',
            'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to',
            'agreements', 'final_submission_date' # Admin can edit agreements too
        ]
        req_text_fields_admin_edit = [f for f in field_list_update_admin if f not in ['middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 'tertiary_course', 'tertiary_year_from', 'tertiary_year_to']]
        req_date_fields_admin_edit = ['date_of_birth', 'date_of_application', 'final_submission_date']

        update_clauses_admin, values_for_update_admin = [], []
        for field in field_list_update_admin:
            val = request.form.get(field)
            if field in req_text_fields_admin_edit and (not val or not val.strip()): flash(f"⚠️ {field.replace('_',' ').title()} required for admin edit.", "danger"); return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
            if field in req_date_fields_admin_edit and not val: flash(f"⚠️ {field.replace('_',' ').title()} date required for admin edit.", "danger"); return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
            # Admin directly sets agreement based on form
            processed_val = val.strip() if val and isinstance(val, str) else val
            if field == 'agreements': processed_val = 'Yes' if val == 'Yes' else 'No' # Explicitly handle checkbox

            update_clauses_admin.append(f"`{field}` = %s"); values_for_update_admin.append(processed_val)
        
        file_fields_admin = {
            'photo': ('2x2 Photo', MAX_PHOTO_SIZE_MB), 
            'shs_diploma_file_input': ('SHS Diploma', MAX_DOC_SIZE_MB),
            'shs_card_file_input': ('SHS Card', MAX_DOC_SIZE_MB),
            'birth_certificate_file_input': ('Birth Certificate', MAX_DOC_SIZE_MB)
        }
        db_file_map_admin = {
            'photo': ['photo'], 
            'shs_diploma_file_input': ['shs_diploma_file', 'shs_diploma_filename', 'shs_diploma_mimetype'],
            'shs_card_file_input': ['shs_card_file', 'shs_card_filename', 'shs_card_mimetype'],
            'birth_certificate_file_input': ['birth_certificate_file', 'birth_certificate_filename', 'birth_certificate_mimetype']
        }

        for form_key, (desc, max_size) in file_fields_admin.items():
            file_storage = request.files.get(form_key)
            if file_storage and file_storage.filename:
                data, fname, mtype, err = process_uploaded_file(file_storage, desc, max_size)
                if err: flash(f"⚠️ {desc} Error: {err}", "danger"); return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
                if data:
                    if form_key == 'photo':
                        update_clauses_admin.append("`photo` = %s"); values_for_update_admin.append(data)
                    else:
                        update_clauses_admin.extend([f"`{db_col}` = %s" for db_col in db_file_map_admin[form_key]])
                        values_for_update_admin.extend([data, fname, mtype])
        
        if not update_clauses_admin: flash("No changes to update.", "info"); return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
        update_clauses_admin.append("`last_updated_at` = %s"); values_for_update_admin.append(datetime.datetime.now())
        
        query_admin = f"UPDATE applicants SET {', '.join(update_clauses_admin)} WHERE applicant_id = %s"
        values_for_update_admin.append(applicant_id)

        cursor = conn.cursor()
        cursor.execute(query_admin, tuple(values_for_update_admin))
        conn.commit()
        flash("✅ App updated by admin!" if cursor.rowcount > 0 else "No changes made by admin.", "success" if cursor.rowcount > 0 else "info")
        return redirect(url_for('auth.admin_dashboard'))

    except Exception as e:
        flash(f"⚠️ Admin Update Error: {e}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.admin_edit_application_page', applicant_id=applicant_id))
    finally:
        if cursor_check: cursor_check.close()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- STUDENT ACCOUNT MANAGEMENT ROUTES -----------------
@auth.route('/change-password', methods=['GET', 'POST'])
def change_password_page(): 
    if 'student_id' not in session: flash("⚠️ Log in to change password.", "warning"); return redirect(url_for('auth.student_login_page'))
    if request.method == 'POST':
        student_user_id = session['student_id']
        current_pass, new_pass, confirm_new = request.form.get('current_password'), request.form.get('new_password'), request.form.get('confirm_new_password')
        if not all([current_pass, new_pass, confirm_new]): flash('Fill all fields.', 'warning'); return redirect(url_for('auth.change_password_page'))
        if new_pass != confirm_new: flash("New passwords don't match.", 'danger'); return redirect(url_for('auth.change_password_page'))
        if len(new_pass) < 8: flash('New password too short.', 'danger'); return redirect(url_for('auth.change_password_page'))
        
        conn = None; cursor = None
        try:
            conn = get_db_connection()
            if not conn: flash("DB error.", "danger"); return redirect(url_for('auth.change_password_page'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT password FROM student_users WHERE id = %s", (student_user_id,))
            user = cursor.fetchone()
            if not user: flash('User not found.', 'danger'); session.clear(); return redirect(url_for('auth.student_login_page'))
            if not check_password_hash(user['password'], current_pass): flash('Incorrect current password.', 'danger'); return redirect(url_for('auth.change_password_page'))
            if check_password_hash(user['password'], new_pass): flash('New password same as current.', 'warning'); return redirect(url_for('auth.change_password_page'))
            
            hashed_new = generate_password_hash(new_pass, method='pbkdf2:sha256')
            cursor.execute("UPDATE student_users SET password = %s, updated_at = NOW() WHERE id = %s", (hashed_new, student_user_id))
            conn.commit()
            flash('✅ Password changed!', 'success')
            return redirect(url_for('views.application_status_page'))
        except Exception as e:
            flash(f'Error changing password: {e}', 'danger'); traceback.print_exc()
            return redirect(url_for('auth.change_password_page'))
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    return render_template('change_password.html')
