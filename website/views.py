from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app
from .auth import get_db_connection, _send_email # Import common db connection function and _send_email
import mysql.connector # Import for error handling
import datetime


views = Blueprint('views', __name__)

# Placeholder data for different programs
# In a real app, this would come from a database.
# Image filenames should correspond to files in your static/images folder.
# Create placeholder images like 'faculty_placeholder_crim1.png' etc., or reuse existing ones.
programs_data_store = {
    "bscs": {
        "id": "bscs",
        "title": "Bachelor of Science in Computer Science",
        "hero_image_filename": "images/bscs.jpg",
        "description": "The Bachelor of Science (B.S.) in Computer Science program at Padre Garcia Polytechnic College is meticulously designed to provide students with a robust and comprehensive understanding of computing principles, software development methodologies, and the theoretical underpinnings of computer science. Our curriculum is crafted to empower graduates with the critical skills necessary to excel in the dynamic and rapidly evolving technology industry, fostering a spirit of innovation, critical thinking, and ethical responsibility in all endeavors.",
        "objectives": [
            "To establish a strong foundational knowledge in mathematical concepts and algorithmic principles that are central to computer science.",
            "To develop advanced proficiency in multiple programming paradigms and a variety of modern programming languages.",
            "To enable students to adeptly design, implement, test, and manage complex software systems, databases, and network infrastructures.",
            "To cultivate superior analytical skills for identifying problems and architecting effective, efficient, and scalable computational solutions.",
            "To thoroughly prepare students for advanced academic pursuits or highly successful careers in diverse technological fields such as software engineering, data science, artificial intelligence, cybersecurity, and cloud computing.",
            "To instill a lifelong commitment to continuous learning, professional growth, and adherence to ethical standards within the computing profession."
        ],
        "career_opportunities": [
            "Software Engineer / Developer (Application, System, Embedded)",
            "Web Developer (Frontend, Backend, Full-Stack)",
            "Mobile Application Developer (iOS, Android)",
            "Data Scientist / Data Analyst / Big Data Engineer",
            "Database Administrator (DBA) / Database Developer",
            "Network Administrator / Network Engineer / Systems Engineer",
            "Cybersecurity Analyst / Information Security Specialist",
            "Game Developer / Game Programmer",
            "Artificial Intelligence (AI) / Machine Learning (ML) Engineer",
            "Cloud Solutions Architect / Cloud Engineer",
            "IT Project Manager / Technical Lead",
            "Systems Analyst / Business Systems Analyst",
            "DevOps Engineer",
            "UX/UI Developer (with strong programming focus)"
        ],
        "core_courses": [
            {"code": "CC 101", "name": "Fundamentals to Computing", "desc": "Introduction to computer systems, history of computing, basic hardware and software concepts, and digital literacy."},
        {"code": "CC 102", "name": "Fundamentals in Programming (e.g., C++)", "desc": "Introduction to programming using C++: syntax, variables, control structures, functions, and debugging."},
        {"code": "GEE 101", "name": "Living in the IT Era", "desc": "Explores the impact of information technology on society, ethics, digital citizenship, and emerging trends."},
        {"code": "CC 103", "name": "Intermediate Programming (e.g., Python/C#)", "desc": "Object-oriented programming, data structures, file handling, and intermediate-level software development."},
        {"code": "CS 121", "name": "Discrete Structure I", "desc": "Fundamentals of logic, set theory, relations, functions, and proof techniques used in computer science."},
        {"code": "CS 122", "name": "Object-Oriented Programming", "desc": "Advanced object-oriented principles, inheritance, polymorphism, and software modeling with UML."},
        {"code": "CSE 101", "name": "Graphics and Visual Computing", "desc": "Introduction to computer graphics, image processing, visualization techniques, and GPU programming basics."},
        {"code": "CC 104", "name": "Data Structure and Algorithms", "desc": "Essential data structures (arrays, lists, trees, graphs) and algorithm analysis (recursion, sorting, searching)."},
        {"code": "CS 211", "name": "Discrete Structure II", "desc": "Combinatorics, graph theory, trees, Boolean algebra, and formal languages."},
        {"code": "DC 101", "name": "Web Development I", "desc": "Fundamentals of HTML, CSS, JavaScript, and basic client-side web programming."},
        {"code": "CS 212", "name": "Automata Theory and Formal Languages", "desc": "Introduction to formal languages, finite automata, regular expressions, and Turing machines."},
        {"code": "CS 213", "name": "Algorithm and Complexity", "desc": "Design and analysis of algorithms, time and space complexity, P vs NP, and optimization problems."},
        {"code": "DC 102", "name": "Web Development II", "desc": "Back-end web development using frameworks, databases, APIs, and deployment techniques."},
        {"code": "DC 103", "name": "System Analysis and Design", "desc": "Systems development life cycle (SDLC), requirements gathering, modeling techniques, and design tools."},
        {"code": "DC 104", "name": "Database Administration and Development", "desc": "Database design, administration, performance tuning, SQL, and handling large-scale data systems."},
        {"code": "DC 105", "name": "Data Science and Fundamentals", "desc": "Introduction to data science, exploratory data analysis, basic statistics, and data visualization tools."},
        {"code": "CS 311", "name": "Architecture and Organization", "desc": "Computer architecture, instruction sets, CPU design, memory hierarchy, and I/O systems."},
        {"code": "CS 312", "name": "Software Engineering I", "desc": "Software development methodologies, requirements engineering, and project planning."},
        {"code": "DC 106", "name": "Introduction to Mobile Application Development", "desc": "Building mobile applications using native and hybrid tools, with a focus on UI/UX and deployment."},
        {"code": "CSE 102", "name": "Parallel and Distributed Computing", "desc": "Principles of parallelism, concurrency, distributed systems, and multithreaded programming."},
        {"code": "MAC 1", "name": "Machine Learning for Structured Data", "desc": "Supervised and unsupervised learning, feature engineering, and model evaluation for structured datasets."},
        {"code": "CSE 103", "name": "Intelligent Systems", "desc": "Fundamentals of AI, expert systems, knowledge representation, and heuristic search techniques."},
        {"code": "CS 321", "name": "Information Assurance and Security", "desc": "Cybersecurity fundamentals, cryptography, risk assessment, and secure software practices."},
        {"code": "CS 322", "name": "Operating System", "desc": "Design and implementation of operating systems, including processes, memory, file systems, and security."},
        {"code": "CS 323", "name": "Software Engineering II", "desc": "Advanced topics in software engineering: quality assurance, maintenance, and software evolution."},
        {"code": "CS 324", "name": "Programming Languages", "desc": "Study of programming paradigms (procedural, object-oriented, functional, logic), and language design."},
        {"code": "CS 325", "name": "Social Issues and Professional Practices", "desc": "Ethical, legal, and societal implications of computing and professional responsibilities."},
        {"code": "MAC 2", "name": "Machine Learning II (Machine Learning for Text Mining)", "desc": "Natural language processing (NLP), text classification, sentiment analysis, and topic modeling."},
        {"code": "CC 106", "name": "Application Development and Emerging Technologies", "desc": "Development of applications using modern frameworks and exploration of trends like IoT, blockchain, and AR/VR."},
        {"code": "CS 421", "name": "Networks and Communication", "desc": "Network architectures, protocols (TCP/IP), routing, switching, and wireless communication."}
        ],
        
        "admission_link_endpoint": "views.existing_or_not"
    },
    "criminology": {
        "id": "criminology",
        "title": "Bachelor of Science in Criminology",
        "hero_image_filename": "images/criminology.jpg",
        "description": "The Bachelor of Science in Criminology program prepares students for careers in law enforcement, corrections, and forensic science. It focuses on the study of crime, criminal behavior, and the justice system, aiming to produce competent and ethical professionals.",
        "objectives": [
            "To provide a comprehensive understanding of criminological theories, criminal law, and justice administration.",
            "To develop critical skills in crime analysis, investigation techniques, and forensic procedures.",
            "To instill a strong sense of ethics, public service, and respect for human rights in future criminologists.",
            "To prepare students for licensure examinations and careers in various fields of criminal justice."
        ],
        "career_opportunities": [
            "Police Officer (PNP, NBI, PDEA)",
            "Correctional Officer (BuCor, BJMP)",
            "Forensic Analyst / Crime Scene Investigator",
            "Probation and Parole Officer",
            "Security Manager / Consultant",
            "Criminologist / Researcher",
            "Private Investigator"
        ],
        "core_courses": [
            {"code": "CRIM 101", "name": "Introduction to Criminology", "desc": "Overview of the field, theories of crime causation, and the nature of crime."},
            {"code": "CRIM 102", "name": "Philippine Criminal Justice System", "desc": "Study of the five pillars of the Philippine criminal justice system."},
            {"code": "CRIM 201", "name": "Criminal Law (Book 1 & 2)", "desc": "Comprehensive study of the Revised Penal Code and related statutes."},
            {"code": "CRIM 205", "name": "Forensic Science & Criminalistics", "desc": "Application of scientific principles to crime detection and investigation."},
        ],
        
        "admission_link_endpoint": "views.existing_or_not"
    },
    "bsma": {
        "id": "bsma",
        "title": "Bachelor of Science in Management Accounting",
        "hero_image_filename": "images/img1.jpg", # Using an existing image from index.html animations
        "description": "The BSMA program equips students with specialized knowledge and skills in financial and managerial accounting, focusing on internal reporting, cost management, and strategic decision support for businesses.",
        "objectives": [
            "To develop expertise in cost accounting, control systems, and financial analysis for internal management.",
            "To train students in preparing financial reports tailored for management decision-making and performance evaluation.",
            "To foster ethical behavior, analytical thinking, and problem-solving skills in accounting practices.",
            "To prepare graduates for careers in corporate accounting, financial planning, and management advisory services."
        ],
        "career_opportunities": [
            "Management Accountant",
            "Cost Analyst / Cost Controller",
            "Financial Controller / Comptroller",
            "Budget Officer / Analyst",
            "Internal Auditor",
            "Financial Planning & Analysis (FP&A) Specialist"
        ],
        "core_courses": [
            {"code": "ACCT 101", "name": "Fundamentals of Accounting Part 1", "desc": "Basic accounting principles, cycle, and financial statement preparation."},
            {"code": "MA 201", "name": "Cost Accounting and Control", "desc": "Study of cost concepts, systems, and their use in planning and control."},
            {"code": "MA 305", "name": "Management Advisory Services", "desc": "Application of accounting and finance concepts to business consulting."},
        ],
       
        "admission_link_endpoint": "views.existing_or_not"
    },
    "bpa": {
        "id": "bpa",
        "title": "Bachelor of Public Administration",
        "hero_image_filename": "images/bpa.jpg",
        "description": "The BPA program is designed for students aspiring to careers in government and public service. It covers public policy, governance, fiscal administration, human resource management, and organizational development in the public sector.",
        "objectives": [
            "To understand the theories, principles, and practices of public administration and good governance.",
            "To develop skills in policy analysis, program planning, implementation, and evaluation in public service.",
            "To promote public service values, ethics, and social responsibility among future public administrators.",
            "To prepare graduates for leadership and management roles in government agencies and non-profit organizations."
        ],
        "career_opportunities": [
            "Public Administrator / Government Officer",
            "Policy Analyst / Researcher",
            "Local Government Unit (LGU) Officer / Staff",
            "Non-profit Organization Manager",
            "Legislative Staff",
            "Human Resource Manager (Public Sector)"
        ],
        "core_courses": [
            {"code": "PA 101", "name": "Introduction to Public Administration", "desc": "Foundations, scope, and evolution of public administration."},
            {"code": "PA 202", "name": "Philippine Administrative System", "desc": "Structure and functions of the Philippine government and bureaucracy."},
            {"code": "PA 301", "name": "Public Policy and Program Administration", "desc": "Process of policy formulation, implementation, and evaluation."},
        ],
       
        "admission_link_endpoint": "views.existing_or_not"
    }
}

# ----------------- HOME PAGE -----------------
@views.route('/')
def home():
    return render_template("index.html", student_logged_in='student_id' in session)

# ----------------- about -----------------
@views.route('/about', methods=['GET', 'POST'])
def about():
    return render_template('about.html', student_logged_in='student_id' in session)

# ----------------- Contact Page -----------------
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
        
        # Validate email format (basic)
        if "@" not in email or "." not in email:
            flash('Please enter a valid email address.', 'danger')
            return redirect(url_for('views.contact_page'))

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
        
        # Use a more descriptive sender name for emails originating from the contact form
        sender_name_override = f"{name} (via PGPC Contact Form)"

        email_sent = _send_email(
            subject=email_subject,
            recipients=[admin_email],
            html_body=email_html_body,
            sender_name_override=sender_name_override # Pass the specific sender name
        )

        if email_sent:
            flash('✅ Thank you for your message! We will get back to you shortly.', 'success')
        else:
            flash('⚠️ Sorry, there was an error sending your message. Please try again later or use an alternative contact method.', 'danger')
        
        return redirect(url_for('views.contact_page'))
    return redirect(url_for('views.contact_page'))


# ----------------- View Program Page -----------------
@views.route('/program/<program_id>')
def view_program_page(program_id):
    program_data = programs_data_store.get(program_id)

    if not program_data:
        flash(f"The program details for '{program_id.upper()}' are not yet available or the program does not exist.", "warning")
        return redirect(url_for('views.home'))

    # Prepare the context for the template, resolving URLs
    program_context = program_data.copy() 
    program_context['hero_image_url'] = url_for('static', filename=program_data['hero_image_filename'])
    program_context['admission_link'] = url_for(program_data['admission_link_endpoint'])
    
    processed_faculty = []
    for member in program_data.get('faculty', []):
        member_copy = member.copy()
        if 'image_filename' in member_copy:
            try:
                member_copy['image_url'] = url_for('static', filename=member_copy['image_filename'])
            except Exception as e:
                print(f"Warning: Could not generate URL for faculty image {member_copy['image_filename']}. Using default. Error: {e}")
                # Ensure you have a 'faculty_placeholder_default.png' in static/images or handle this differently
                member_copy['image_url'] = url_for('static', filename='images/faculty_placeholder1.png') # Fallback to a known placeholder
        processed_faculty.append(member_copy)
    program_context['faculty'] = processed_faculty
    
    return render_template(
        "view_program.html",
        program=program_context, # This 'program' object will be used by view_program.html
        student_logged_in='student_id' in session
    )

# ----------------- existing_or_not (Entry point for application) -----------------
@views.route('/application-status')
def application_status_page():
    if 'student_id' not in session:
        flash("⚠️ Please log in to view your application status.", "warning")
        return redirect(url_for('auth.student_login_page'))

    student_user_id = session['student_id']
    application_data = None
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 
                    applicant_id, first_name, last_name, program_choice, 
                    application_status, email_address, submitted_at,
                    admin_notes, decision_date,
                    permit_control_no, permit_exam_date, permit_exam_time, permit_testing_room,
                    photo, middle_name, date_of_birth, place_of_birth, sex, civil_status,
                    academic_year, senior_high_school, senior_high_school_track_strand, senior_high_school_year_to,
                    exam_status 
                FROM applicants 
                WHERE student_user_id = %s 
                ORDER BY submitted_at DESC 
                LIMIT 1
            """, (student_user_id,))
            application_data = cursor.fetchone()
        
        if not application_data:
            flash("No application found for your account. Please submit one.", "info")
            return redirect(url_for('views.new_student')) 

    except mysql.connector.Error as err:
        flash(f"Database Error: {err}", "danger")
        print(f"Database error in application_status_page: {err}") 
        return redirect(url_for('views.home'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        print(f"Unexpected error in application_status_page: {e}")
        return redirect(url_for('views.home'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template(
        "pending_application.html", 
        application=application_data, 
        student_logged_in='student_id' in session
    )

@views.route('/existing_or_not', methods=['GET', 'POST'])
def existing_or_not():
    if 'student_id' in session:
        return redirect(url_for('views.application_status_page'))
    return render_template('existing_or_not.html', student_logged_in='student_id' in session)

# ----------------- new_student (Application Form) -----------------
@views.route('/new-student')
def new_student():
    if 'student_id' not in session:
        flash("⚠️ Please log in to access the application form.", "warning")
        return redirect(url_for('auth.student_login_page'))
    
    today_date_str = datetime.date.today().strftime('%Y-%m-%d')
    return render_template(
        'new_student.html', 
        student_logged_in='student_id' in session,
        today_date_for_form=today_date_str
    )