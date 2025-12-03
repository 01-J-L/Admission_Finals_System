# --- START OF FILE views.py ---

from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app
from .auth import get_db_connection, _send_email, _get_active_term, _get_program_list, _is_email_trigger_enabled
import mysql.connector # Import for error handling
import datetime
import traceback


views = Blueprint('views', __name__)

def _get_program_details_from_db(program_id=None):
    """Fetches all programs or a single program with all related details from the database."""
    conn = None
    cursor = None
    programs = {}
    try:
        conn = get_db_connection()
        if not conn: return {} if program_id is None else None
        
        cursor = conn.cursor(dictionary=True)
        
        base_query = "SELECT * FROM programs"
        params = []
        if program_id:
            base_query += " WHERE program_id = %s"
            params.append(program_id)
        
        cursor.execute(base_query, tuple(params))
        programs_list = cursor.fetchall()

        for p in programs_list:
            current_program_id = p['program_id']
            # Add a 'id' key to match old data structure if needed by templates
            p['id'] = current_program_id
            programs[current_program_id] = p
            
            # Fetch related data
            cursor.execute("SELECT objective_text FROM program_objectives WHERE program_id = %s", (current_program_id,))
            programs[current_program_id]['objectives'] = [row['objective_text'] for row in cursor.fetchall()]

            cursor.execute("SELECT career_text FROM program_careers WHERE program_id = %s", (current_program_id,))
            programs[current_program_id]['career_opportunities'] = [row['career_text'] for row in cursor.fetchall()]

            cursor.execute("SELECT course_code, course_name, course_description as `desc` FROM program_courses WHERE program_id = %s ORDER BY id", (current_program_id,))
            programs[current_program_id]['core_courses'] = cursor.fetchall()

    except Exception as e:
        print(f"Database error in _get_program_details_from_db: {e}")
        traceback.print_exc()
        return {} if program_id is None else None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    if program_id:
        return programs.get(program_id)
    return programs

# ----------------- HOME PAGE -----------------
@views.route('/')
def home():
    programs_from_db = list(_get_program_details_from_db().values())
    news_articles = []
    announcements = []
    hero_slides = []
    admission_steps = [] 
    faqs = []
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM news_articles ORDER BY publish_date DESC, id DESC")
            news_articles = cursor.fetchall()
            
            cursor.execute("SELECT title, content, created_at, image_filename FROM announcements WHERE is_active = TRUE ORDER BY created_at DESC")
            announcements = cursor.fetchall()

            cursor.execute("SELECT * FROM hero_slides WHERE is_active = TRUE ORDER BY sort_order ASC, id DESC")
            hero_slides = cursor.fetchall()

            cursor.execute("SELECT * FROM admission_steps ORDER BY step_number ASC")
            admission_steps = cursor.fetchall()

            cursor.execute("SELECT * FROM faqs ORDER BY sort_order ASC")
            faqs = cursor.fetchall()

    except Exception as e:
        print(f"Error fetching homepage data: {e}")
        traceback.print_exc()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return render_template("index.html", 
                           student_logged_in='student_id' in session,
                           programs=programs_from_db,
                           news_articles=news_articles,
                           announcements=announcements,
                           hero_slides=hero_slides,
                           admission_steps=admission_steps,
                           faqs=faqs)

# ----------------- ABOUT -----------------
@views.route('/about', methods=['GET', 'POST'])
def about():
    faculty_by_category = {'leadership': [], 'faculty': [], 'support': []}
    page_content = {} 
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT name, role, image_filename, category FROM faculty ORDER BY category, id")
            all_faculty = cursor.fetchall()
            for member in all_faculty:
                if member['category'] in faculty_by_category:
                    faculty_by_category[member['category']].append(member)
            
            cursor.execute("SELECT content_key, content_value FROM page_content")
            content_rows = cursor.fetchall()
            page_content = {row['content_key']: row['content_value'] for row in content_rows}

    except Exception as e:
        print(f"Error fetching about page data: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('about.html', 
                           student_logged_in='student_id' in session,
                           faculty_data=faculty_by_category,
                           content=page_content)

@views.app_context_processor
def inject_global_content():
    conn = None
    cursor = None
    global_content = {}
    global_requirements = {}
    global_socials = []  # Initialize list

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Fetch Page Content (Existing)
            keys = (
                'contact_email', 'contact_phone', 'contact_address', 'contact_map_url', 'contact_hours',
                'footer_title', 'footer_subtitle', 'footer_connect_text', 'footer_facebook_link', 'footer_logo_image',
                'consent_title', 'consent_text', 'oath_title', 'oath_text',
                'sidebar_info_title', 'sidebar_info_1', 'sidebar_info_2', 'sidebar_info_3',
                'sidebar_contact_title', 'sidebar_phone_label', 'sidebar_email_label', 'sidebar_email_value', 'sidebar_hours_label', 'sidebar_hours_value',
                'status_msg_pending', 'status_msg_review', 'status_msg_approved', 
                'status_msg_rejected', 'status_msg_passed', 'status_msg_failed', 
                'status_msg_enrolling', 'status_msg_enrolled', 'status_msg_dropped', 
                'status_msg_not_enrolled', 'requirements_header_text'
            )
            format_strings = ','.join(['%s'] * len(keys))
            cursor.execute(f"SELECT content_key, content_value FROM page_content WHERE content_key IN ({format_strings})", keys)
            rows = cursor.fetchall()
            global_content = {row['content_key']: row['content_value'] for row in rows}

            # 2. Fetch Registration Status (Existing)
            cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'registration_open'")
            reg_row = cursor.fetchone()
            global_content['registration_open'] = reg_row['setting_value'] if reg_row else 'true' 

            # 3. Fetch Requirements (Existing)
            cursor.execute("SELECT * FROM status_requirements ORDER BY id ASC")
            req_rows = cursor.fetchall()
            from collections import defaultdict
            requirements_dict = defaultdict(list)
            for row in req_rows:
                requirements_dict[row['status_key']].append(row)
            global_requirements = requirements_dict

            # 4. NEW: Fetch Social Media Links
            cursor.execute("SELECT * FROM social_media_links")
            global_socials = cursor.fetchall()

    except Exception as e:
        print(f"Error injecting global content: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return dict(
        global_content=global_content, 
        global_requirements=global_requirements,
        global_socials=global_socials # <--- THIS MUST BE HERE
    )

# ----------------- CONTACT PAGE -----------------
@views.route('/contact', methods=['GET'])
def contact_page():
    return render_template('contact.html', student_logged_in='student_id' in session)

@views.route('/submit-contact-form', methods=['POST'])
def submit_contact_form():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject_user = request.form.get('subject')
        message_user = request.form.get('message')

        if not all([name, email, subject_user, message_user]):
            flash('Please fill out all fields in the contact form.', 'danger')
            return redirect(url_for('views.contact_page'))
        
        if "@" not in email or "." not in email:
            flash('Please enter a valid email address.', 'danger')
            return redirect(url_for('views.contact_page'))

        # --- CHECK ADMIN EMAIL TRIGGER ---
        if not _is_email_trigger_enabled('email_trigger_admin'):
            # If admin emails are off, we just acknowledge the submission but don't send the email
            print(f"Admin email trigger disabled. Skipping contact form email from {email}.")
            flash('✅ Thank you for your message! We have received your submission.', 'success')
            return redirect(url_for('views.contact_page'))
        # ---------------------------------

        admin_email = current_app.config.get('ADMIN_EMAIL')
        if not admin_email:
            flash('The system is not configured to receive messages currently. Please try alternative contact methods.', 'danger')
            print("CRITICAL: ADMIN_EMAIL not configured. Contact form submission failed.")
            return redirect(url_for('views.contact_page'))

        email_subject = f"Contact Form Submission: {subject_user}"
        
        email_html_body = f"""
        <h3>New Contact Form Submission</h3>
        <p>You have received a new message from your website's contact form:</p>
        <hr>
        <p><strong>Name:</strong> {name}</p>
        <p><strong>Email:</strong> {email}</p>
        <p><strong>Subject:</strong> {subject_user}</p>
        <p><strong>Message:</strong></p>
        <p style="white-space: pre-wrap;">{message_user}</p>
        <hr>
        <p><small>This message was sent on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</small></p>
        """
        
        sender_name_override = f"{name} (via PGPC Contact Form)"

        email_sent = _send_email(
            subject=email_subject,
            recipients=[admin_email],
            html_body=email_html_body,
            sender_name_override=sender_name_override
        )

        if email_sent:
            flash('✅ Thank you for your message! We will get back to you shortly.', 'success')
        else:
            flash('⚠️ Sorry, there was an error sending your message. Please try again later or use an alternative contact method.', 'danger')
        
        return redirect(url_for('views.contact_page'))
    return redirect(url_for('views.contact_page'))


# ----------------- VIEW PROGRAM PAGE -----------------
@views.route('/program/<program_id>')
def view_program_page(program_id):
    program_data = _get_program_details_from_db(program_id)

    if not program_data:
        flash(f"The program details for '{program_id.upper()}' are not yet available or the program does not exist.", "warning")
        return redirect(url_for('views.home'))

    program_context = program_data.copy()
    if program_data.get('hero_image_filename'):
        program_context['hero_image_url'] = url_for('static', filename=f"images/uploads/{program_data['hero_image_filename']}")
    else:
        program_context['hero_image_url'] = url_for('static', filename='images/default_program_hero.jpg')

    program_context['admission_link'] = url_for(program_data.get('admission_link_endpoint', 'views.existing_or_not'))
    
    return render_template(
        "view_program.html",
        program=program_context,
        student_logged_in='student_id' in session
    )

# ----------------- APPLICATION STATUS PAGE -----------------
@views.route('/application-status')
def application_status_page():
    if 'student_id' not in session:
        flash("⚠️ Please log in to view your application status.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    application_data = None
    current_term_grades = []
    status_downloads = [] 
    active_term = _get_active_term()
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # Fetch main application data with Section Name
            cursor.execute("""
                SELECT 
                    a.applicant_id, a.first_name, a.last_name, a.program_choice, 
                    a.application_status, a.email_address, a.submitted_at,
                    a.admin_notes, a.decision_date,
                    a.permit_control_no, a.permit_exam_date, a.permit_exam_time, a.permit_testing_room,
                    a.photo, a.middle_name, a.date_of_birth, a.place_of_birth, a.sex, a.civil_status,
                    a.academic_year, a.senior_high_school, a.senior_high_school_track_strand, a.senior_high_school_year_to,
                    a.exam_status, a.old_student_id, a.student_user_id, a.control_number,
                    a.original_enrollment_status, a.enrollment_year_level, a.enrollment_semester,
                    p.program_id as program_code,
                    s.section_name 
                FROM applicants a
                LEFT JOIN programs p ON a.program_choice = p.title
                LEFT JOIN sections s ON a.section_id = s.id
                WHERE a.student_user_id = %s 
                ORDER BY a.submitted_at DESC 
                LIMIT 1
            """, (student_user_id,))
            application_data = cursor.fetchone()
        
        # --- CRITICAL FIX: Check if application exists before accessing it ---
        if not application_data:
            flash("No application found for your account. Please submit one.", "info")
            return redirect(url_for('views.new_student'))
        # -------------------------------------------------------------------

        # --- Fetch Status Downloads ---
        status_key_map = {
            'Pending': 'status_msg_pending',
            'In Review': 'status_msg_review',
            'Approved': 'status_msg_approved',
            'Scheduled': 'status_msg_scheduled',
            'Rejected': 'status_msg_rejected',
            'Passed': 'status_msg_passed',
            'Failed': 'status_msg_failed',
            'Enrolling': 'status_msg_enrolling',
            'Enrolled': 'status_msg_enrolled',
            'Dropped': 'status_msg_dropped',
            'Not Enrolled': 'status_msg_not_enrolled',
            'Eligible for Enrollment': 'status_msg_enrolling'
        }
        
        # It is now safe to access application_data
        current_status_key = status_key_map.get(application_data['application_status'])
        
        if current_status_key and conn:
            program_id = application_data.get('program_code')
            cursor.execute("""
                SELECT * FROM status_uploads 
                WHERE status_key = %s 
                AND (program_id IS NULL OR program_id = %s OR program_id = '')
            """, (current_status_key, program_id))
            status_downloads = cursor.fetchall()

        # --- Fetch Grades (Only for Enrolled/Enrolling/Dropped) ---
        if application_data.get('application_status') in ['Enrolled', 'Enrolling', 'Dropped'] and active_term and conn:
            try:
                cursor.execute("""
                    SELECT s.subject_code, s.subject_title, sg.grade, sg.remarks
                    FROM student_grades sg
                    JOIN subjects s ON sg.subject_id = s.id
                    WHERE sg.student_user_id = %s
                    AND sg.academic_year = %s
                    AND sg.semester = %s
                    ORDER BY s.subject_code ASC
                """, (
                    application_data['student_user_id'],
                    active_term['year_name'],
                    active_term['semester']
                ))
                current_term_grades = cursor.fetchall()
            except Exception as e_grades:
                print(f"Error fetching grades: {e_grades}")
                traceback.print_exc()

    except mysql.connector.Error as err:
        flash(f"Database Error: {err}", "danger")
        print(f"Database error in application_status_page: {err}") 
        return redirect(url_for('views.home'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        print(f"Unexpected error in application_status_page: {e}")
        traceback.print_exc() # Print detailed error to console
        return redirect(url_for('views.home'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template(
        "pending_application.html", 
        application=application_data, 
        current_term_grades=current_term_grades,
        status_downloads=status_downloads,
        active_term=active_term,
        student_logged_in='student_id' in session
    )

# ----------------- EXISTING OR NOT -----------------
@views.route('/existing_or_not', methods=['GET', 'POST'])
def existing_or_not():
    active_term = _get_active_term()
    if not active_term:
        flash("Admissions are currently closed. Please check back later.", "warning")
        return redirect(url_for('views.home'))

    if 'student_id' in session:
        student_user_id = session['student_id']
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT applicant_id FROM applicants 
                    WHERE student_user_id = %s 
                    AND application_status IN ('Pending', 'In Review', 'Approved', 'Passed', 'Scheduled')
                """, (student_user_id,))
                
                active_application = cursor.fetchone()

                if active_application:
                    flash("You already have an active application. Here is its status.", "info")
                    return redirect(url_for('views.application_status_page'))
                else:
                    return redirect(url_for('views.new_student'))
            
        except mysql.connector.Error as err:
            flash(f"Database Error: Could not check application status. {err}", "danger")
            return redirect(url_for('views.home'))
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    
    return render_template('existing_or_not.html', student_logged_in='student_id' in session)

# ----------------- ENROLLMENT FORMS -----------------
# Use _get_program_list to populate dropdown in both enrollment forms

@views.route('/enrollment-form/<int:applicant_id>', methods=['GET'])
def enrollment_form_page(applicant_id):
    if 'student_id' not in session:
        flash("⚠️ Please log in to access the enrollment form.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('views.application_status_page'))
            
        cursor = conn.cursor(dictionary=True)
        # Fetch application data, including section name
        cursor.execute("""
            SELECT 
                a.applicant_id, a.first_name, a.last_name, a.middle_name, a.email_address, a.program_choice, 
                a.academic_year, a.application_status, a.date_of_birth, a.place_of_birth, a.sex, a.civil_status,
                a.religion, a.mobile_number, a.permanent_address_street_barangay, a.permanent_address_city_municipality,
                a.permanent_address_province, a.senior_high_school, a.senior_high_school_year_from,
                a.senior_high_school_year_to, a.father_name, a.father_occupation, a.father_contact_number,
                a.mother_maiden_name, a.mother_occupation, a.mother_contact_number,
                a.guardian_name, a.guardian_contact_number,
                a.shs_diploma_file, a.shs_card_file, a.birth_certificate_file, a.photo,
                a.original_enrollment_status, a.student_user_id, a.old_student_id, a.control_number,
                a.section_id, a.is_section_permanent, a.enrollment_student_type, a.enrollment_year_level,
                s.section_name
            FROM applicants a
            LEFT JOIN sections s ON a.section_id = s.id
            WHERE a.applicant_id = %s AND a.student_user_id = %s
        """, (applicant_id, student_user_id))
        application = cursor.fetchone()
        
        if not application:
            flash("Application not found or you do not have permission.", "danger")
            return redirect(url_for('views.application_status_page'))
        
        # Determine if this is a re-enrollment (Existing Student progressing)
        is_re_enrollment = application.get('original_enrollment_status') == 'Enrolled'

        # ALLOWED STATUSES: Passed (New), Enrolling (Draft), Eligible (Re-enrolling)
        if application['application_status'] not in ['Passed', 'Enrolling', 'Eligible for Enrollment']:
            flash(f"This application is not ready for enrollment (Status: {application['application_status']}).", "warning")
            return redirect(url_for('views.application_status_page'))
            
        # Fetch Active Term
        active_term = _get_active_term() 
        
        # Fetch Programs for Dropdown
        all_programs = _get_program_list()

        if is_re_enrollment:
            return render_template('re_enrollment_form.html', 
                                   application=application, 
                                   programs=all_programs,
                                   active_term=active_term, 
                                   active_school_year=active_term['year_name'] if active_term else application.get('academic_year'),
                                   student_logged_in=True)

        # Logic for New / First-time Enrollment
        docs_submitted = {
            'diploma': bool(application.get('shs_diploma_file')),
            'card': bool(application.get('shs_card_file')),
            'birth_cert': bool(application.get('birth_certificate_file')),
            'photo': bool(application.get('photo'))
        }

        return render_template('enrollment_form.html', 
                               application=application, 
                               docs_submitted=docs_submitted, 
                               programs=all_programs,
                               active_term=active_term,
                               student_logged_in=True)

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for('views.application_status_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# ----------------- NEW STUDENT (Application Form) -----------------
@views.route('/new-student')
def new_student():
    if 'student_id' not in session:
        flash("⚠️ Please log in to access the application form.", "warning")
        return redirect(url_for('auth.student_login_page'))
    
    active_term = _get_active_term()
    if not active_term:
        flash("Admissions are currently closed. Please check back later.", "warning")
        return redirect(url_for('views.home'))
    
    student_user_id = session['student_id']
    student_type = 'new'
    old_student_id = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT student_type, old_student_id FROM student_users WHERE id = %s", (student_user_id,))
            user_data = cursor.fetchone()
            if user_data:
                student_type = user_data.get('student_type', 'new')
                old_student_id = user_data.get('old_student_id')
    except Exception as e:
        print(f"Error fetching student type for new application form: {e}")
        traceback.print_exc()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    all_programs = list(_get_program_details_from_db().values())
    student_email_from_session = session.get('student_email', '') 
    today_date_str = datetime.date.today().strftime('%Y-%m-%d')
    return render_template(
        'new_student.html', 
        student_logged_in='student_id' in session,
        today_date_for_form=today_date_str,
        student_email=student_email_from_session,
        programs=all_programs,
        student_type=student_type,
        old_student_id=old_student_id,
        active_school_year=active_term['year_name']
    )