# --- START OF FILE views.py ---

from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app
from .auth import get_db_connection, _send_email, _get_active_term, _get_program_list, _is_email_trigger_enabled
import mysql.connector # Import for error handling
import datetime
import traceback
from collections import defaultdict
from .auth import get_db_connection, _get_active_term, _get_program_list, _calculate_next_term


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

# --- OPEN FILE: views.py ---
@views.route('/my-statement')
def view_student_statement():
    if 'student_id' not in session:
        flash("⚠️ Please log in to view your statement of account.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    conn = None
    cursor = None
    assessments = []
    payments = []
    student_info = None
    total_balance = 0.0
    
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return redirect(url_for('views.application_status_page'))
        
        cursor = conn.cursor(dictionary=True)
        
        # 1. Get Applicant ID and Basic Info
        # MODIFIED: Added * to ensure all fields needed by header are present
        cursor.execute("""
            SELECT *
            FROM applicants 
            WHERE student_user_id = %s
            ORDER BY submitted_at DESC
            LIMIT 1
        """, (student_user_id,))
        student_info = cursor.fetchone()

        if not student_info:
            flash("No application record found.", "warning")
            return redirect(url_for('views.application_status_page'))
            
        applicant_id_db = student_info['applicant_id']
        
        # Add display_id logic if missing in DB fetch (needed for template)
        student_info['display_id'] = student_info['old_student_id'] or student_info['control_number'] or 'N/A'

        # 2. Fetch Assessments
        cursor.execute("""
            SELECT * FROM assessments 
            WHERE student_id = %s 
            ORDER BY created_at DESC
            LIMIT 10
        """, (applicant_id_db,))
        assessments = cursor.fetchall()

        # 3. Fetch Payment History
        cursor.execute("""
            SELECT * FROM payments 
            WHERE student_id = %s 
            ORDER BY payment_date DESC
            LIMIT 10
        """, (applicant_id_db,))
        payments = cursor.fetchall()

        # 4. Calculate Total
        cursor.execute("""
            SELECT SUM(balance) as total_bal 
            FROM assessments 
            WHERE student_id = %s
        """, (applicant_id_db,))
        bal_res = cursor.fetchone()
        total_balance = float(bal_res['total_bal']) if bal_res['total_bal'] else 0.0

    except Exception as e:
        print(f"Error fetching statement: {e}")
        traceback.print_exc()
        flash("An error occurred loading your financial records.", "danger")
        return redirect(url_for('views.application_status_page'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('student_statement.html', 
                           student=student_info, 
                           application=student_info,
                           assessments=assessments, 
                           payments=payments,
                           total_balance=total_balance,
                           now=datetime.datetime.now(),
                           student_logged_in=True)

@views.app_context_processor
def inject_global_content():
    conn = None
    cursor = None
    global_content = {}
    global_socials = [] # This holds our links
    global_requirements = defaultdict(list)
    
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            # 1. Fetch Page Content (Text fields)
            keys = ('contact_email', 'contact_phone', 'contact_address', 'contact_map_url', 'contact_hours',
                    'footer_title', 'footer_subtitle', 'footer_connect_text', 'footer_facebook_link', 'footer_logo_image',
                    'consent_title', 'consent_text', 'oath_title', 'oath_text',
                    'sidebar_info_title', 'sidebar_info_1', 'sidebar_info_2', 'sidebar_info_3',
                    'sidebar_contact_title', 'sidebar_phone_label', 'sidebar_email_label', 'sidebar_email_value', 'sidebar_hours_label', 'sidebar_hours_value',
                    'status_msg_pending', 'status_msg_review', 'status_msg_approved', 
                    'status_msg_scheduled', 'status_msg_rejected', 'status_msg_passed', 'status_msg_failed', 
                    'status_msg_enrolling', 'status_msg_enrolled', 'status_msg_dropped', 
                    'status_msg_not_enrolled', 'requirements_header_text')
            
            format_strings = ','.join(['%s'] * len(keys))
            cursor.execute(f"SELECT content_key, content_value FROM page_content WHERE content_key IN ({format_strings})", keys)
            rows = cursor.fetchall()
            global_content = {row['content_key']: row['content_value'] for row in rows}
            
            # 2. Fetch System Settings (Toggles)
            cursor.execute("SELECT setting_key, setting_value FROM system_settings")
            for row in cursor.fetchall():
                global_content[row['setting_key']] = row['setting_value']

            # 3. Fetch Social Media Links for the footer
            cursor.execute("SELECT platform_name, url, icon_class FROM social_media_links ORDER BY platform_name ASC")
            global_socials = cursor.fetchall()

            # 4. Fetch Status Requirements
            cursor.execute("SELECT status_key, requirement_text FROM status_requirements")
            for row in cursor.fetchall():
                global_requirements[row['status_key']].append(row)

    except Exception as e:
        print(f"Error injecting global content: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return dict(global_content=global_content, global_socials=global_socials, global_requirements=global_requirements)

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

@views.route('/student/resources')
def student_resources():
    if 'student_id' not in session:
        flash("Please log in to access resources.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    conn = None
    cursor = None
    grouped_files = defaultdict(list)
    student_info = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Get Student's Academic Info
        # MODIFIED: Select * or specific fields needed for the header (applicant_id, first_name, last_name, etc)
        cursor.execute("""
            SELECT a.*, s.section_name
            FROM applicants a
            LEFT JOIN sections s ON a.section_id = s.id
            WHERE a.student_user_id = %s
            ORDER BY a.submitted_at DESC LIMIT 1
        """, (student_user_id,))
        student_info = cursor.fetchone()

        if student_info:
            my_program = student_info['program_choice']
            my_year = student_info['enrollment_year_level']
            my_section = student_info['section_name'] or 'Unassigned'
            
            # 2. Fetch files
            query = """
                SELECT * FROM student_downloads 
                WHERE 
                    (target_program = 'All' OR target_program = %s)
                AND 
                    (target_year_level = 'All' OR target_year_level = %s)
                AND 
                    (target_section = 'All' OR target_section = %s)
                ORDER BY category, uploaded_at DESC
            """
            cursor.execute(query, (my_program, my_year, my_section))
            files = cursor.fetchall()

            for f in files:
                grouped_files[f['category']].append(f)

    except Exception as e:
        print(f"Error fetching resources: {e}")
        traceback.print_exc()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('student_downloads.html', 
                           grouped_files=grouped_files,
                           application=student_info, 
                           student_logged_in=True) 


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
            # Fetch main application data
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
        
        # --- Redirect Logic based on Status ---
        if not application_data:
            # Quit during new student form -> Send back to New Student Form
            flash("Please complete your application form.", "info")
            return redirect(url_for('views.new_student'))
        
        if application_data['application_status'] == 'Passed':
            # Quit during enrollment form (Old or New passed) -> Send back to Enrollment Form
            flash("Please complete your enrollment details.", "info")
            return redirect(url_for('views.enrollment_form_page', applicant_id=application_data['applicant_id']))
        # --------------------------------------

        # --- SECTION VISIBILITY LOGIC (NEW) ---
        # Only show section if status is 'Enrolled'
        if application_data['application_status'] != 'Enrolled':
            application_data['section_name'] = None
        # --------------------------------------

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
        return redirect(url_for('views.home'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        traceback.print_exc()
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
    # 1. Security Check: Ensure user is logged in
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
        
        # 2. Fetch application data and ensure the logged-in student owns this record
        cursor.execute("""
            SELECT * FROM applicants 
            WHERE applicant_id = %s AND student_user_id = %s
        """, (applicant_id, student_user_id))
        application = cursor.fetchone()
        
        if not application:
            flash("Application not found or you do not have permission to access it.", "danger")
            return redirect(url_for('views.application_status_page'))
        
        # 3. Check if the student is eligible to see the form
        # 'Passed' = New student cleared for enrollment
        # 'Eligible for Enrollment' = Old student cleared for the next term
        # 'Enrolling' = Student who has already clicked "Proceed" but hasn't finished the form
        allowed_statuses = ['Passed', 'Enrolling', 'Eligible for Enrollment']
        if application['application_status'] not in allowed_statuses:
            flash(f"This application is not ready for enrollment (Status: {application['application_status']}).", "warning")
            return redirect(url_for('views.application_status_page'))
            
        # 4. Fetch prerequisites for the forms
        active_term = _get_active_term() 
        all_programs = _get_program_list()

        # 5. Check if this is a Re-enrollment (Existing student returning for a new term)
        # We check the original_enrollment_status set during the term-opening process
        is_re_enrollment = application.get('original_enrollment_status') == 'Enrolled'

        # =========================================================
        # BRANCH A: RE-ENROLLMENT LOGIC (Continuing Students)
        # =========================================================
        if is_re_enrollment:
            curr_year = application.get('enrollment_year_level')
            curr_sem = application.get('enrollment_semester')
            
            # Calculate next academic level (e.g. 1st Year 2nd Sem -> 2nd Year 1st Sem)
            # Function imported from auth.py
            next_year, next_sem, is_graduating = _calculate_next_term(curr_year, curr_sem)

            return render_template('re_enrollment_form.html', 
                                   application=application, 
                                   active_term=active_term,
                                   active_school_year=active_term['year_name'] if active_term else application.get('academic_year'),
                                   student_logged_in=True,
                                   projected_year=next_year,
                                   projected_sem=next_sem,
                                   is_graduating=is_graduating,
                                   programs=all_programs)

        # =========================================================
        # BRANCH B: NEW STUDENT ENROLLMENT LOGIC (Initial Enrollment)
        # =========================================================
        else:
            # Calculate Age from Date of Birth for auto-filling the inventory part of the form
            age_val = ''
            if application.get('date_of_birth'):
                from datetime import date
                today = date.today()
                dob = application['date_of_birth']
                # Standard age formula
                age_val = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

            # Determine which documents were already provided during the initial application step
            # This allows the frontend to show "Previously Submitted" status
            docs_submitted = {
                'diploma': bool(application.get('shs_diploma_file')),
                'card': bool(application.get('shs_card_file')),
                'birth_cert': bool(application.get('birth_certificate_file')),
                'photo': bool(application.get('photo'))
            }

            return render_template('enrollment_form.html', 
                                   application=application, 
                                   calculated_age=age_val, 
                                   docs_submitted=docs_submitted, 
                                   programs=all_programs,
                                   active_term=active_term,
                                   student_logged_in=True)

    except Exception as e:
        print(f"Error loading enrollment form: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred loading the enrollment form. Please try again.", "danger")
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