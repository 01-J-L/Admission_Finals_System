from flask import Blueprint, render_template, request, flash, redirect, session, url_for, jsonify, current_app # Added current_app
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
from datetime import timedelta
import base64
import traceback
import secrets
from flask_mail import Message # Message is already here
import os

# ----------------- BLUEPRINT SETUP -----------------
auth = Blueprint('auth', __name__)

# ----------------- DATABASE CONNECTION -----------------
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', "anime951827"), # Ensure this matches your .env
            database=os.getenv('DB_NAME', "ayusin")     # Ensure this matches your .env
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        traceback.print_exc() # Print full traceback for DB connection errors
        return None

# ----------------- EMAIL SENDING HELPER FUNCTIONS -----------------
def _send_email(subject, recipients, html_body, sender_name_override=None):
    """Generic email sending function."""
    mail_handler = current_app.extensions.get('mail')
    
    if not mail_handler:
        print("CRITICAL: Flask-Mail is not configured or initialized. Email not sent.")
        return False
    if not current_app.config.get('MAIL_USERNAME') or not current_app.config.get('MAIL_PASSWORD'):
        print("CRITICAL: MAIL_USERNAME or MAIL_PASSWORD not configured. Email not sent.")
        return False

    # Determine the sender name for this specific email
    # Use sender_name_override if provided, else use MAIL_SENDER_NAME, else use MAIL_DEFAULT_SENDER name part
    effective_sender_name = sender_name_override
    if not effective_sender_name:
        effective_sender_name = current_app.config.get('MAIL_SENDER_NAME') # From .env MAIL_SENDER_NAME
    
    # Construct the sender tuple (Name, Email) or just Email string
    default_sender_config = current_app.config.get('MAIL_DEFAULT_SENDER')
    sender_email_address = None
    if isinstance(default_sender_config, tuple):
        sender_email_address = default_sender_config[1]
        if not effective_sender_name: # If no override and MAIL_SENDER_NAME wasn't set
            effective_sender_name = default_sender_config[0]
    elif isinstance(default_sender_config, str):
        sender_email_address = default_sender_config
    
    if not sender_email_address: # Fallback if MAIL_DEFAULT_SENDER was not set properly
        sender_email_address = current_app.config.get('MAIL_USERNAME')
        print(f"Warning: MAIL_DEFAULT_SENDER not fully configured, using MAIL_USERNAME ({sender_email_address}) as sender email.")

    if not effective_sender_name: # Final fallback for sender name
        effective_sender_name = "PGPC System"


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

def send_application_status_email(applicant_email, applicant_name, new_status, application_id, program_choice=None):
    """Sends email about application status change."""
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    app_id_formatted = f"P2025{application_id:04d}"
    subject = ""
    template_name = ""

    if new_status == 'Approved':
        subject = f"Application {app_id_formatted} Approved - {sender_name_from_config}"
        template_name = 'email/application_approved_email.html'
    elif new_status == 'Rejected':
        subject = f"Application {app_id_formatted} Update - {sender_name_from_config}"
        template_name = 'email/application_rejected_email.html'
    else:
        print(f"Email not sent: Status '{new_status}' does not trigger notification for P2025{application_id:04d}.")
        return False

    html_body = render_template(
        template_name,
        applicant_name=applicant_name,
        application_id_formatted=app_id_formatted,
        program_choice=program_choice,
        sender_name=sender_name_from_config, # This is used inside the email template
        now=datetime.datetime.now()
    )
    return _send_email(subject, [applicant_email], html_body, sender_name_override=sender_name_from_config)


def send_password_reset_email(user_email, token):
    """Sends password reset email."""
    sender_name_from_config = current_app.config.get('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')
    try:
        # SERVER_NAME must be configured in app.config for _external=True to work without request context
        reset_url = url_for('auth.reset_password_page', token=token, _external=True)
    except RuntimeError as e:
        if "Application context" in str(e) or "SERVER_NAME" in str(e):
            print(f"CRITICAL: Cannot generate external reset URL. Ensure FLASK_SERVER_NAME is set in .env and app.config['SERVER_NAME'] is configured. Error: {e}")
            flash("Password reset system error. Admin has been notified.", "danger") # Generic message
            return False, None # Return email_sent_status and reset_url_for_dev_log
        raise e


    subject = f"Password Reset Request - {sender_name_from_config}"
    html_body = render_template(
        'email/reset_password_email.html',
        reset_url=reset_url,
        user_email=user_email,
        sender_name=sender_name_from_config,
        now=datetime.datetime.now()
    )
    email_sent = _send_email(subject, [user_email], html_body, sender_name_override=sender_name_from_config)
    return email_sent, reset_url


# ----------------- ADMIN ROUTES -----------------

@auth.route('/admin/application/<int:applicant_id>/notes', methods=['POST'])
def admin_save_application_notes(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    notes = request.form.get('notes', '')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE applicants SET admin_notes = %s, last_updated_at = NOW() WHERE applicant_id = %s",
            (notes, applicant_id)
        )
        conn.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True, "message": f"Notes for application P2025{applicant_id:04d} saved successfully."})
        else:
            cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
            if cursor.fetchone()[0] > 0:
                 return jsonify({"success": True, "message": "Notes saved (no change detected or application updated)."})
            return jsonify({"success": False, "message": "Application not found."}), 404
    except mysql.connector.Error as err:
        print(f"DB Error saving notes for applicant_id {applicant_id}: {err}")
        return jsonify({"success": False, "message": "Database error while saving notes."}), 500
    except Exception as e:
        print(f"Unexpected error saving notes for applicant_id {applicant_id}: {e}")
        return jsonify({"success": False, "message": f"Unexpected server error: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/admin/application/<int:applicant_id>/permit-details', methods=['POST'])
def admin_save_permit_details(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    permit_control_no = request.form.get('permit_control_no')
    permit_exam_date_str = request.form.get('permit_exam_date')
    permit_exam_time = request.form.get('permit_exam_time')
    permit_testing_room = request.form.get('permit_testing_room')

    permit_exam_date = None
    if permit_exam_date_str and permit_exam_date_str.strip():
        try:
            permit_exam_date = datetime.datetime.strptime(permit_exam_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"success": False, "message": "Invalid date format for exam date. Use YYYY-MM-DD."}), 400
    
    permit_control_no = permit_control_no if permit_control_no and permit_control_no.strip() else None
    permit_exam_time = permit_exam_time if permit_exam_time and permit_exam_time.strip() else None
    permit_testing_room = permit_testing_room if permit_testing_room and permit_testing_room.strip() else None

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        cursor = conn.cursor()
        cursor.execute("""
            UPDATE applicants
            SET permit_control_no = %s,
                permit_exam_date = %s,
                permit_exam_time = %s,
                permit_testing_room = %s,
                last_updated_at = NOW()
            WHERE applicant_id = %s
        """, (permit_control_no,
              permit_exam_date,
              permit_exam_time,
              permit_testing_room,
              applicant_id))
        conn.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True, "message": f"Permit details for P2025{applicant_id:04d} saved."})
        else:
            cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
            if cursor.fetchone()[0] > 0:
                return jsonify({"success": True, "message": "Permit details saved (no change detected or application updated)."})
            return jsonify({"success": False, "message": "Application not found."}), 404
    except mysql.connector.Error as err:
        print(f"DB Error saving permit details for applicant_id {applicant_id}: {err}")
        return jsonify({"success": False, "message": "Database error while saving permit details."}), 500
    except Exception as e:
        print(f"Unexpected error saving permit details for applicant_id {applicant_id}: {e}")
        return jsonify({"success": False, "message": f"Unexpected server error: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/control-number', methods=['POST'])
def admin_save_control_number(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    control_number = request.form.get('control_number')
    control_number = control_number if control_number and control_number.strip() else None

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE applicants SET control_number = %s, last_updated_at = NOW() WHERE applicant_id = %s",
            (control_number, applicant_id)
        )
        conn.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True, "message": f"Control number for P2025{applicant_id:04d} saved."})
        else:
            cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
            if cursor.fetchone()[0] > 0:
                 return jsonify({"success": True, "message": "Control number saved (no change detected or application updated)."})
            return jsonify({"success": False, "message": "Application not found."}), 404
    except mysql.connector.Error as err:
        print(f"DB Error saving control number for {applicant_id}: {err}")
        return jsonify({"success": False, "message": "Database error."}), 500
    except Exception as e:
        print(f"Unexpected error saving control number for {applicant_id}: {e}")
        return jsonify({"success": False, "message": "Unexpected server error."}), 500
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

    # !!! SECURITY RISK: Hardcoded credentials. Replace with a proper admin user system.
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin') 
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin')

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        flash("✅ Admin login successful!", "success")
        return redirect(url_for('auth.admin_dashboard'))
    else:
        flash('Invalid admin credentials', "danger")
        return redirect(url_for('auth.admin'))


# ----------------- STUDENT AUTHENTICATION ROUTES -----------------

@auth.route('/create-student-account', methods=['GET'])
def create_student_account_page():
    if 'student_id' in session: 
        return redirect(url_for('views.application_status_page'))
    return render_template('create_account.html')

@auth.route('/create-student-account', methods=['POST'])
def create_student_account_action():
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if not email or not password or not confirm_password:
        flash('Please fill out all fields.', 'warning')
        return redirect(url_for('auth.create_student_account_page'))

    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('auth.create_student_account_page'))

    if len(password) < 8:
        flash('Password must be at least 8 characters long.', 'danger')
        return redirect(url_for('auth.create_student_account_page'))

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.create_student_account_page'))

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM student_users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('Email already registered. Please login or use a different email.', 'danger')
            return redirect(url_for('auth.create_student_account_page'))

        cursor.execute(
            "INSERT INTO student_users (email, password) VALUES (%s, %s)",
            (email, hashed_password)
        )
        conn.commit()
        flash('✅ Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.student_login_page'))
    except mysql.connector.Error as err:
        flash(f'⚠️ Database Error: {err}', 'danger')
        return redirect(url_for('auth.create_student_account_page'))
    except Exception as e:
        flash(f'⚠️ Error: {str(e)}', 'danger')
        return redirect(url_for('auth.create_student_account_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/student-login', methods=['GET'])
def student_login_page():
    if 'student_id' in session: 
        return redirect(url_for('views.application_status_page'))
    return render_template('student_login.html')

@auth.route('/student-login', methods=['POST'])
def student_login_action():
    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not password:
        flash('Please fill out all fields.', 'warning')
        return redirect(url_for('auth.student_login_page'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.student_login_page'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM student_users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['student_id'] = user['id']
            session['student_email'] = user['email']
            flash('✅ Login successful!', 'success')
            return redirect(url_for('views.application_status_page')) 
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            return redirect(url_for('auth.student_login_page'))
    except mysql.connector.Error as err:
        flash(f'⚠️ Database Error: {err}', 'danger')
        return redirect(url_for('auth.student_login_page'))
    except Exception as e:
        flash(f'⚠️ Error: {str(e)}', 'danger')
        return redirect(url_for('auth.student_login_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- STUDENT FORGOT/RESET PASSWORD ROUTES -----------------

@auth.route('/forgot-password', methods=['GET'])
def forgot_password_request_page():
    return render_template('forgot_password_request.html')

@auth.route('/forgot-password', methods=['POST'])
def forgot_password_request_action():
    email = request.form.get('email')
    if not email:
        flash("Please enter your email address.", "warning")
        return redirect(url_for('auth.forgot_password_request_page'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error. Please try again.", "danger")
            return redirect(url_for('auth.forgot_password_request_page'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM student_users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        email_sent_status = False
        reset_url_for_dev_log = None # Variable to hold reset_url for logging

        if user: # User exists in the database
            token = secrets.token_urlsafe(32)
            expiry_time = datetime.datetime.now() + timedelta(hours=1) 

            cursor.execute(
                "UPDATE student_users SET reset_token = %s, reset_token_expiry = %s WHERE id = %s",
                (token, expiry_time, user['id'])
            )
            conn.commit()
            
            email_sent_status, reset_url_for_dev_log = send_password_reset_email(email, token)
            
            if email_sent_status:
                flash(f"A password reset link has been sent to {email}. Please check your inbox (and spam folder).", "success")
                print(f"Password reset email successfully dispatched to {email}. Link: {reset_url_for_dev_log}")
            else:
                flash(f"We encountered an issue sending the email. Please try again later or contact support.", "danger")
                if reset_url_for_dev_log: # Log the link even if email failed, for admin use
                     print(f"Failed to send reset email to {email}. For admin/dev reference, the link would be: {reset_url_for_dev_log}")
                else: # This means url_for itself failed due to SERVER_NAME config
                     print(f"Failed to generate or send reset email to {email} due to URL generation error (check FLASK_SERVER_NAME).")
        else: 
            flash(f"⚠️ The email address '{email}' is not registered. Please check the email or create an account.", "danger")
            print(f"Password reset requested for non-existent email: {email}")
        
        return redirect(url_for('auth.forgot_password_request_page'))

    except mysql.connector.Error as err:
        if err.errno == 1054: 
            flash('⚠️ Password reset feature is not fully configured (DB schema). Please contact admin.', 'danger')
            print(f"CRITICAL: Missing 'reset_token' or 'reset_token_expiry' columns in 'student_users' table. Error: {err}")
        else:
            flash(f'⚠️ Database Error: {err}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.forgot_password_request_page'))
    except Exception as e:
        flash(f'⚠️ An unexpected error occurred: {str(e)}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.forgot_password_request_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.forgot_password_request_page'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, reset_token_expiry FROM student_users WHERE reset_token = %s", (token,)
        )
        user = cursor.fetchone()

        if not user:
            flash("Invalid password reset token. It may have already been used or is incorrect.", "danger")
            return redirect(url_for('auth.forgot_password_request_page'))

        expiry_time = user.get('reset_token_expiry')
        if not isinstance(expiry_time, datetime.datetime):
            try:
                if expiry_time:
                    expiry_time = datetime.datetime.strptime(str(expiry_time), '%Y-%m-%d %H:%M:%S')
                else: 
                    flash("Invalid token state. Please request a new reset link.", "danger")
                    return redirect(url_for('auth.forgot_password_request_page'))
            except (ValueError, TypeError):
                 flash("Error processing token expiry. Please request a new reset link.", "danger")
                 return redirect(url_for('auth.forgot_password_request_page'))

        if expiry_time < datetime.datetime.now():
            flash("Password reset token has expired. Please request a new one.", "danger")
            cursor.execute("UPDATE student_users SET reset_token = NULL, reset_token_expiry = NULL WHERE id = %s", (user['id'],))
            conn.commit()
            return redirect(url_for('auth.forgot_password_request_page'))
        
        return render_template('reset_password_form.html', token=token)
    except mysql.connector.Error as err:
        if err.errno == 1054:
             flash('⚠️ Password reset feature is not fully configured (DB schema). Please contact admin.', 'danger')
        else:
            flash(f'⚠️ Database Error: {err}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.forgot_password_request_page'))
    except Exception as e:
        flash(f'⚠️ An unexpected error occurred: {str(e)}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.forgot_password_request_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/reset-password/<token>', methods=['POST'])
def reset_password_action(token):
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if not password or not confirm_password:
        flash("Please fill out all fields.", "warning")
        return redirect(url_for('auth.reset_password_page', token=token))
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return redirect(url_for('auth.reset_password_page', token=token))
    if len(password) < 8: 
        flash('Password must be at least 8 characters long.', 'danger')
        return redirect(url_for('auth.reset_password_page', token=token))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.reset_password_page', token=token))

        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, reset_token_expiry FROM student_users WHERE reset_token = %s", (token,)
        )
        user = cursor.fetchone()

        if not user:
            flash("Invalid password reset token. It may have already been used or is incorrect.", "danger")
            return redirect(url_for('auth.forgot_password_request_page'))

        expiry_time = user.get('reset_token_expiry')
        if not isinstance(expiry_time, datetime.datetime):
            try:
                if expiry_time:
                    expiry_time = datetime.datetime.strptime(str(expiry_time), '%Y-%m-%d %H:%M:%S')
                else:
                    flash("Invalid token state. Please request a new reset link.", "danger")
                    return redirect(url_for('auth.forgot_password_request_page'))
            except (ValueError, TypeError):
                 flash("Error processing token expiry. Please request a new reset link.", "danger")
                 return redirect(url_for('auth.forgot_password_request_page'))

        if expiry_time < datetime.datetime.now():
            flash("Password reset token has expired. Please request a new one.", "danger")
            cursor.execute("UPDATE student_users SET reset_token = NULL, reset_token_expiry = NULL WHERE id = %s", (user['id'],))
            conn.commit()
            return redirect(url_for('auth.forgot_password_request_page'))
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        cursor.execute(
            "UPDATE student_users SET password = %s, reset_token = NULL, reset_token_expiry = NULL WHERE id = %s",
            (hashed_password, user['id'])
        )
        conn.commit()
        flash('✅ Password has been reset successfully! Please log in with your new password.', 'success')
        return redirect(url_for('auth.student_login_page'))
    except mysql.connector.Error as err:
        if err.errno == 1054:
             flash('⚠️ Password reset feature is not fully configured (DB schema). Please contact admin.', 'danger')
        else:
            flash(f'⚠️ Database Error: {err}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.reset_password_page', token=token))
    except Exception as e:
        flash(f'⚠️ An unexpected error occurred: {str(e)}', 'danger')
        traceback.print_exc()
        return redirect(url_for('auth.reset_password_page', token=token))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- APPLICATION FORM SUBMISSION (NEW STUDENT) -----------------
@auth.route('/submit_application', methods=['POST'])
def submit_application():
    if 'student_id' not in session:
        flash("⚠️ You must be logged in to submit an application.", "warning")
        return redirect(url_for('auth.student_login_page'))

    if request.method != 'POST':
        return redirect(url_for('views.new_student')) 

    conn = None
    cursor = None
    student_user_id = session['student_id']
    
    try:
        photo_file = request.files.get('photo')
        photo_data = None
        if photo_file and photo_file.filename != '':
            MAX_FILE_SIZE = 5 * 1024 * 1024 
            photo_data_read = photo_file.read() 
            if len(photo_data_read) > MAX_FILE_SIZE:
                flash("⚠️ Photo file is too large (max 5MB). Please upload a smaller file.", "danger")
                return redirect(url_for('views.new_student'))
            photo_data = photo_data_read
        else: 
            flash("⚠️ A 2x2 Photo is required for the application.", "danger")
            return redirect(url_for('views.new_student'))

        field_list_from_form = [
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
        
        db_columns_for_insert = [
            'student_user_id', 'program_choice', 'last_name', 'first_name', 'middle_name', 'date_of_birth', 'place_of_birth',
            'sex', 'civil_status', 'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 
            'control_number', 
            'date_of_application', 'academic_year', 'average_family_income', 
            'father_name', 'father_occupation', 'father_company_address', 'father_contact_number', 
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number', 
            'guardian_name', 'guardian_occupation', 'guardian_company_address', 'guardian_contact_number', 
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand', 
            'senior_high_school_year_from', 'senior_high_school_year_to', 
            'tertiary_school', 'tertiary_school_address', 'tertiary_course',
            'tertiary_year_from', 'tertiary_year_to', 'agreements', 'final_submission_date',
            'photo', 'application_status', 'submitted_at'
        ]

        strictly_required_text_fields = [
            'program_choice', 'last_name', 'first_name', 'place_of_birth', 'sex', 'civil_status',
            'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'academic_year',
            'average_family_income', 'father_name', 'father_occupation', 
            'father_company_address', 'father_contact_number',
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number',
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand',
            'senior_high_school_year_from', 'senior_high_school_year_to', 'agreements'
        ]
        required_date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date']
        optional_text_fields = [
            'middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 
            'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 
            'tertiary_course', 'tertiary_year_from', 'tertiary_year_to'
        ]

        form_values_processed = []
        for field_name in field_list_from_form: 
            value = request.form.get(field_name)
            if field_name in strictly_required_text_fields:
                if not value or (isinstance(value, str) and not value.strip()):
                    flash(f"⚠️ {field_name.replace('_', ' ').capitalize()} is a required field.", "danger")
                    return redirect(url_for('views.new_student'))
                if field_name == 'agreements' and value != 'Yes': 
                    flash("⚠️ You must agree to the terms and conditions.", "danger")
                    return redirect(url_for('views.new_student'))
                processed_value = value.strip() if isinstance(value, str) else value
            elif field_name in required_date_fields:
                if not value: 
                    flash(f"⚠️ {field_name.replace('_', ' ').capitalize()} is a required date.", "danger")
                    return redirect(url_for('views.new_student'))
                processed_value = value 
            elif field_name in optional_text_fields:
                processed_value = value.strip() if value and value.strip() else None
            else:
                flash(f"⚠️ Internal error processing field '{field_name}'. Contact support.", "danger")
                print(f"WARNING: Uncategorized form field '{field_name}' in submit_application.")
                return redirect(url_for('views.new_student'))
            form_values_processed.append(processed_value)
        
        values_for_query_map = dict(zip(field_list_from_form, form_values_processed))
        final_values_for_insert = []
        for db_col in db_columns_for_insert:
            if db_col == 'student_user_id': final_values_for_insert.append(student_user_id)
            elif db_col == 'control_number': final_values_for_insert.append(None) 
            elif db_col == 'photo': final_values_for_insert.append(photo_data)
            elif db_col == 'application_status': final_values_for_insert.append('Pending')
            elif db_col == 'submitted_at': final_values_for_insert.append(datetime.datetime.now())
            elif db_col in values_for_query_map: final_values_for_insert.append(values_for_query_map[db_col])
            else:
                print(f"CRITICAL SERVER ERROR: Unmapped DB column '{db_col}' during insert prep.")
                flash("⚠️ Internal Error: Data processing mismatch. Please contact support.", "danger")
                return redirect(url_for('views.new_student'))

        if len(final_values_for_insert) != len(db_columns_for_insert):
            flash(f"⚠️ Internal Error: Data column count mismatch. Please contact support.", "danger")
            return redirect(url_for('views.new_student'))

        conn = get_db_connection()
        if not conn:
            flash("Database connection error. Please try again later.", "danger")
            return redirect(url_for('views.new_student'))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT applicant_id FROM applicants
            WHERE student_user_id = %s AND (application_status = 'Pending' OR application_status = 'In Review')
        """, (student_user_id,))
        if cursor.fetchone():
            flash("⚠️ You already have an active application. Please wait for it to be processed or check its status.", "warning")
            return redirect(url_for('views.application_status_page'))

        placeholders = ', '.join(['%s'] * len(db_columns_for_insert))
        cols_str = '`, `'.join(db_columns_for_insert) 
        query_to_execute = f"INSERT INTO applicants (`{cols_str}`) VALUES ({placeholders})"
        
        cursor.execute(query_to_execute, tuple(final_values_for_insert))
        conn.commit()
        flash("✅ Application submitted successfully! You can check your application status now.", "success")
        return redirect(url_for('views.application_status_page'))
    except mysql.connector.Error as err:
        flash(f"⚠️ Database Error: {err}. If problem persists, contact support.", "danger")
        traceback.print_exc()
        return redirect(url_for('views.new_student'))
    except KeyError as e:
        flash(f"⚠️ Session Error: Missing information ({e}). Please log in again.", "danger")
        traceback.print_exc()
        return redirect(url_for('auth.student_login_page'))
    except Exception as e:
        flash(f"⚠️ An unexpected error occurred: {str(e)}. Please try again or contact support.", "danger")
        traceback.print_exc()
        return redirect(url_for('views.new_student'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- ADMIN APPLICATION MANAGEMENT API ROUTES -----------------
@auth.route('/admin/application/<int:applicant_id>/status', methods=['POST'])
def admin_update_application_status(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    new_status = request.form.get('status')
    valid_statuses = ['Pending', 'In Review', 'Approved', 'Rejected']

    if not new_status or new_status not in valid_statuses:
        return jsonify({"success": False, "message": "Invalid status provided"}), 400

    conn = None
    app_info_cursor = None
    update_cursor = None
    check_again_cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        # Fetch student's email and name BEFORE updating status
        app_info_cursor = conn.cursor(dictionary=True)
        app_info_cursor.execute("""
            SELECT 
                a.first_name, a.last_name, a.program_choice,
                su.email as student_account_email, 
                a.email_address as application_form_email
            FROM applicants a
            LEFT JOIN student_users su ON a.student_user_id = su.id
            WHERE a.applicant_id = %s
        """, (applicant_id,))
        applicant_info = app_info_cursor.fetchone()

        if not applicant_info:
            return jsonify({"success": False, "message": "Application not found, cannot update status."}), 404

        student_email_to_notify = applicant_info.get('student_account_email') or applicant_info.get('application_form_email')
        applicant_name = f"{applicant_info.get('first_name', '')} {applicant_info.get('last_name', '')}".strip()
        program_choice = applicant_info.get('program_choice')
        
        # Perform the status update
        current_time = datetime.datetime.now()
        update_cursor = conn.cursor()
        if new_status in ['Approved', 'Rejected']:
            update_cursor.execute("""
                UPDATE applicants SET application_status = %s, decision_date = %s, last_updated_at = %s
                WHERE applicant_id = %s
            """, (new_status, current_time, current_time, applicant_id))
        else: 
            update_cursor.execute("""
                UPDATE applicants SET application_status = %s, decision_date = NULL, last_updated_at = %s
                WHERE applicant_id = %s
            """, (new_status, current_time, applicant_id))
        
        conn.commit()
        rows_affected = update_cursor.rowcount

        if rows_affected > 0:
            email_sent_successfully = False
            if new_status in ['Approved', 'Rejected'] and student_email_to_notify:
                email_sent_successfully = send_application_status_email(
                    student_email_to_notify, applicant_name, new_status, applicant_id, program_choice
                )
            
            response_message = f"Application P2025{applicant_id:04d} status updated to {new_status}."
            if new_status in ['Approved', 'Rejected'] and student_email_to_notify:
                response_message += " Email notification sent." if email_sent_successfully else " Failed to send email notification."
            
            return jsonify({
                "success": True, "message": response_message,
                "new_status": new_status, "applicant_id": applicant_id
            })
        else:
            check_again_cursor = conn.cursor()
            check_again_cursor.execute("SELECT COUNT(*) FROM applicants WHERE applicant_id = %s", (applicant_id,))
            if check_again_cursor.fetchone()[0] > 0:
                 return jsonify({"success": True, "message": f"Status for P2025{applicant_id:04d} is already {new_status} or no effective change.", "new_status": new_status, "applicant_id": applicant_id})
            return jsonify({"success": False, "message": "Application not found"}), 404
            
    except mysql.connector.Error as err:
        print(f"DB Error updating status for P2025{applicant_id:04d}: {err}")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Database error during status update."}), 500
    except Exception as e:
        print(f"Unexpected error during status update for P2025{applicant_id:04d}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Unexpected server error: {e}"}), 500
    finally:
        if app_info_cursor: app_info_cursor.close()
        if update_cursor: update_cursor.close()
        if check_again_cursor: check_again_cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/delete', methods=['POST'])
def admin_delete_application(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        cursor = conn.cursor()
        cursor.execute("DELETE FROM applicants WHERE applicant_id = %s", (applicant_id,))
        conn.commit()

        if cursor.rowcount > 0:
            return jsonify({"success": True, "message": f"Application P2025{applicant_id:04d} deleted successfully."})
        else:
            return jsonify({"success": False, "message": "Application not found"}), 404
    except mysql.connector.Error as err:
        print(f"DB Error deleting application: {err}")
        return jsonify({"success": False, "message": "Database error while deleting"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@auth.route('/admin/application/<int:applicant_id>/details', methods=['GET'])
def admin_get_application_details(applicant_id):
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection error"}), 500

        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.*, su.email as student_account_email
            FROM applicants a
            LEFT JOIN student_users su ON a.student_user_id = su.id
            WHERE a.applicant_id = %s
        """, (applicant_id,))
        application = cursor.fetchone()

        if application:
            for key, value in application.items():
                if isinstance(value, (datetime.datetime, datetime.date)):
                    application[key] = value.isoformat()
                elif key == 'photo' and isinstance(value, bytes):
                    if value: 
                        try:
                            img_format = "jpeg" 
                            if value.startswith(b'\x89PNG\r\n\x1a\n'): img_format = "png"
                            elif value.startswith(b'\xFF\xD8\xFF'): img_format = "jpeg"
                            application[key] = f"data:image/{img_format};base64,{base64.b64encode(value).decode('utf-8')}"
                        except Exception as e_photo:
                            print(f"Error base64 encoding photo for applicant_id {applicant_id}: {e_photo}")
                            application[key] = "Error displaying photo" 
                    else:
                        application[key] = None 
                elif isinstance(value, bytes): 
                    application[key] = f"Binary data (length: {len(value)}) - Not displayed"
            return jsonify({"success": True, "data": application})
        else:
            return jsonify({"success": False, "message": "Application not found"}), 404
    except mysql.connector.Error as err:
        print(f"DB Error fetching details for applicant_id {applicant_id}: {err}")
        return jsonify({"success": False, "message": "Database error"}), 500
    except Exception as e:
        print(f"Unexpected error fetching details for applicant_id {applicant_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Unexpected server error: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash("⚠️ Please log in first to access the admin dashboard.", "warning")
        return redirect(url_for('auth.admin'))

    applications_data = []
    stats = {
        'total_applications': 0, 'pending': 0, 'in_review': 0,
        'approved': 0, 'rejected': 0,
    }

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    a.applicant_id, a.first_name, a.last_name, a.email_address,
                    a.program_choice, a.date_of_application, a.application_status,
                    a.submitted_at, a.decision_date,
                    su.email as student_account_email
                FROM applicants a
                LEFT JOIN student_users su ON a.student_user_id = su.id
                ORDER BY
                    CASE
                        WHEN a.application_status = 'Pending' THEN 1
                        WHEN a.application_status = 'In Review' THEN 2
                        ELSE 3
                    END,
                    a.submitted_at DESC, a.applicant_id DESC
            """)
            raw_applications_data = cursor.fetchall() # Store raw for JSON
            
            # Process for display in template (dates to Python datetime if not already)
            applications_data = []
            for app_dict in raw_applications_data:
                new_app_dict = app_dict.copy()
                for key, value in new_app_dict.items():
                    if isinstance(value, str): # Dates might be strings from DB if not auto-converted
                        if key in ['date_of_application', 'submitted_at', 'decision_date']:
                            try:
                                # Try parsing with time, then without if it fails
                                dt_obj = datetime.datetime.fromisoformat(value.replace('Z', '+00:00')) if 'T' in value else datetime.datetime.strptime(value, '%Y-%m-%d')
                                new_app_dict[key] = dt_obj
                            except (ValueError, TypeError):
                                pass # Keep original string if parsing fails
                applications_data.append(new_app_dict)


            cursor.execute("SELECT COUNT(*) as total FROM applicants")
            total_res = cursor.fetchone()
            if total_res: stats['total_applications'] = total_res['total']

            cursor.execute("SELECT application_status, COUNT(*) as count FROM applicants GROUP BY application_status")
            status_counts = cursor.fetchall()
            for row in status_counts:
                status_key = row['application_status'].lower().replace(' ', '_')
                if status_key in stats:
                    stats[status_key] = row['count']
        else:
            flash("Database connection error.", "danger")

    except mysql.connector.Error as err:
        flash(f"Database Error: {err}", "danger")
        print(f"Database Error in admin_dashboard: {err}")
        traceback.print_exc()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    # Pass raw_applications_data for JS charts, applications_data for Jinja table rendering
    return render_template('admin_dashboard.html', applications=applications_data, stats=stats, raw_application_data_for_js=raw_applications_data)


@auth.route('/applicant-photo/<int:applicant_id>')
def get_applicant_photo(applicant_id):
    is_admin = session.get('admin_logged_in', False)
    student_user_id_session = session.get('student_id', None)

    if not is_admin and not student_user_id_session:
        return "Unauthorized", 401 

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return "DB error", 500
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT photo, student_user_id FROM applicants WHERE applicant_id = %s", (applicant_id,))
        app_data = cursor.fetchone()

        if not app_data: return "Not found", 404
        if not is_admin and (app_data['student_user_id'] != student_user_id_session):
             return "Forbidden", 403

        if app_data['photo']:
            content_type = 'image/jpeg' 
            if app_data['photo'].startswith(b'\x89PNG\r\n\x1a\n'): content_type = 'image/png'
            from flask import Response
            return Response(app_data['photo'], mimetype=content_type)
        else:
            return "No photo available", 404
    except mysql.connector.Error as e:
        print(f"Error fetching photo for applicant {applicant_id}: {e}")
        return "Server error", 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- STUDENT APPLICATION EDIT ROUTES -----------------
# (Keep your existing student application edit routes as they were)
@auth.route('/edit-application/<int:applicant_id>', methods=['GET'])
def edit_application_page(applicant_id):
    if 'student_id' not in session:
        flash("⚠️ Please log in to edit your application.", "warning")
        return redirect(url_for('auth.student_login_page'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('views.application_status_page'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM applicants WHERE applicant_id = %s AND student_user_id = %s",
                       (applicant_id, session['student_id']))
        application = cursor.fetchone()

        if not application:
            flash("Application not found or you do not have permission to edit it.", "danger")
            return redirect(url_for('views.application_status_page'))

        editable_statuses = ['Pending', 'In Review'] 
        if application['application_status'] not in editable_statuses:
            flash(f"Your application with status '{application['application_status']}' cannot be edited.", "warning")
            return redirect(url_for('views.application_status_page'))

        date_fields_to_format = ['date_of_birth', 'date_of_application', 'final_submission_date']
        for field_name in date_fields_to_format:
            if application.get(field_name) and isinstance(application[field_name], (datetime.date, datetime.datetime)):
                application[field_name] = application[field_name].isoformat().split('T')[0]
        
        return render_template('edit_application.html', 
                               application=application, 
                               student_logged_in='student_id' in session)
    except mysql.connector.Error as err:
        flash(f"Database Error: {err}", "danger"); traceback.print_exc()
        return redirect(url_for('views.application_status_page'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger"); traceback.print_exc()
        return redirect(url_for('views.application_status_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@auth.route('/update-application/<int:applicant_id>', methods=['POST'])
def update_application_action(applicant_id):
    if 'student_id' not in session:
        flash("⚠️ You must be logged in to update an application.", "warning")
        return redirect(url_for('auth.student_login_page'))

    conn = None; cursor_check = None; cursor = None
    student_user_id = session['student_id']

    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))

        cursor_check = conn.cursor(dictionary=True)
        cursor_check.execute("SELECT student_user_id, application_status FROM applicants WHERE applicant_id = %s", (applicant_id,))
        app_to_edit = cursor_check.fetchone()
        
        if not app_to_edit:
            flash("Application not found.", "danger")
            return redirect(url_for('views.application_status_page'))
        if app_to_edit['student_user_id'] != student_user_id:
            flash("You do not have permission to edit this application.", "danger")
            return redirect(url_for('views.application_status_page'))
        
        editable_statuses = ['Pending', 'In Review']
        if app_to_edit['application_status'] not in editable_statuses:
            flash(f"This application (status: {app_to_edit['application_status']}) can no longer be edited.", "warning")
            return redirect(url_for('views.application_status_page'))
        
        cursor_check.close() # Important to close before potentially opening another

        field_list_for_update = [
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
        strictly_required_text_fields = [
            'program_choice', 'last_name', 'first_name', 'place_of_birth', 'sex', 'civil_status',
            'religion', 'citizenship', 'mobile_number', 'email_address',
            'permanent_address_street_barangay', 'permanent_address_city_municipality',
            'permanent_address_province', 'permanent_address_postal_code',
            'cultural_minority_group', 'physical_disability', 'academic_year',
            'average_family_income', 'father_name', 'father_occupation', 
            'father_company_address', 'father_contact_number',
            'mother_maiden_name', 'mother_occupation', 'mother_company_address', 'mother_contact_number',
            'senior_high_school', 'senior_high_school_address', 'senior_high_school_track_strand',
            'senior_high_school_year_from', 'senior_high_school_year_to', 'agreements'
        ]
        required_date_fields = ['date_of_birth', 'date_of_application', 'final_submission_date']
        optional_text_fields = [
            'middle_name', 'guardian_name', 'guardian_occupation', 'guardian_company_address', 
            'guardian_contact_number', 'tertiary_school', 'tertiary_school_address', 
            'tertiary_course', 'tertiary_year_from', 'tertiary_year_to'
        ]

        update_clauses = []
        values_for_update = []
        for field_name in field_list_for_update:
            value = request.form.get(field_name)
            processed_value = None
            if field_name in strictly_required_text_fields:
                if not value or (isinstance(value, str) and not value.strip()):
                    flash(f"⚠️ {field_name.replace('_', ' ').capitalize()} is required.", "danger")
                    return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
                if field_name == 'agreements' and value != 'Yes':
                    flash("⚠️ You must re-agree to the terms.", "danger")
                    return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
                processed_value = value.strip() if isinstance(value, str) else value
            elif field_name in required_date_fields:
                if not value:
                    flash(f"⚠️ {field_name.replace('_', ' ').capitalize()} is a required date.", "danger")
                    return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
                processed_value = value 
            elif field_name in optional_text_fields:
                processed_value = value.strip() if value and value.strip() else None
            else:
                 flash(f"⚠️ Internal error processing field '{field_name}'.", "danger")
                 return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
            update_clauses.append(f"`{field_name}` = %s")
            values_for_update.append(processed_value)

        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename != '':
            MAX_FILE_SIZE = 5 * 1024 * 1024
            photo_data_read = photo_file.read()
            if len(photo_data_read) > MAX_FILE_SIZE:
                flash("⚠️ Photo file too large (max 5MB).", "danger")
                return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
            update_clauses.append("`photo` = %s")
            values_for_update.append(photo_data_read)
        
        if not update_clauses:
            flash("No changes detected.", "info")
            return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))

        update_clauses.append("`last_updated_at` = %s")
        values_for_update.append(datetime.datetime.now())

        query = f"UPDATE applicants SET {', '.join(update_clauses)} WHERE applicant_id = %s AND student_user_id = %s"
        values_for_update.extend([applicant_id, student_user_id])
        
        cursor = conn.cursor()
        cursor.execute(query, tuple(values_for_update))
        conn.commit()

        flash("✅ Application updated successfully!" if cursor.rowcount > 0 else "No data changed.", "success" if cursor.rowcount > 0 else "info")
        return redirect(url_for('views.application_status_page'))
    except mysql.connector.Error as err:
        flash(f"⚠️ Database Error: {err}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
    except Exception as e:
        flash(f"⚠️ Unexpected Error: {str(e)}", "danger"); traceback.print_exc()
        return redirect(url_for('auth.edit_application_page', applicant_id=applicant_id))
    finally:
        if cursor_check:
            cursor_check.close()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- STUDENT ACCOUNT MANAGEMENT ROUTES -----------------
# (Keep your existing student account management routes as they were)
@auth.route('/change-password', methods=['GET'])
def change_password_page():
    if 'student_id' not in session:
        flash("⚠️ Please log in to change your password.", "warning")
        return redirect(url_for('auth.student_login_page'))
    return render_template('change_password.html')

@auth.route('/change-password', methods=['POST'])
def change_password_action():
    if 'student_id' not in session:
        flash("⚠️ Session expired. Please log in again.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_new_password = request.form.get('confirm_new_password')

    if not all([current_password, new_password, confirm_new_password]):
        flash('Please fill out all password fields.', 'warning')
        return redirect(url_for('auth.change_password_page'))
    if new_password != confirm_new_password:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('auth.change_password_page'))
    if len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'danger')
        return redirect(url_for('auth.change_password_page'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('auth.change_password_page'))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM student_users WHERE id = %s", (student_user_id,))
        user = cursor.fetchone()

        if not user:
            flash('User account not found. Please log in again.', 'danger')
            session.clear()
            return redirect(url_for('auth.student_login_page'))
        if not check_password_hash(user['password'], current_password):
            flash('Incorrect current password.', 'danger')
            return redirect(url_for('auth.change_password_page'))
        if check_password_hash(user['password'], new_password):
            flash('New password cannot be the same as the current password.', 'warning')
            return redirect(url_for('auth.change_password_page'))

        hashed_new_password = generate_password_hash(new_password, method='pbkdf2:sha256')
        cursor.execute("UPDATE student_users SET password = %s WHERE id = %s", (hashed_new_password, student_user_id))
        conn.commit()
        flash('✅ Password changed successfully!', 'success')
        return redirect(url_for('views.application_status_page'))
    except mysql.connector.Error as err:
        flash(f'⚠️ Database Error: {err}', 'danger'); traceback.print_exc()
        return redirect(url_for('auth.change_password_page'))
    except Exception as e:
        flash(f'⚠️ An unexpected error occurred: {str(e)}', 'danger'); traceback.print_exc()
        return redirect(url_for('auth.change_password_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()