from flask import Flask
from flask_mail import Mail
from dotenv import load_dotenv # Import python-dotenv
import os

# Load environment variables from .env file
load_dotenv()

mail = Mail() # Initialize mail here or within create_app

def create_app():
    app = Flask(__name__)

    # --- Flask App Configuration ---
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_default_fallback_secret_key')
    app.debug = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

    # --- File Upload Configuration ---
    # Create the folder if it doesn't exist
    upload_folder = os.path.join(app.root_path, 'static', 'images', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max upload size


    # --- Email Configuration ---
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587)) # Ensure port is integer
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'False').lower() in ('true', '1', 't')
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    
    # MAIL_DEFAULT_SENDER can be a string or a tuple (Name, Email)
    default_sender_email = os.getenv('MAIL_DEFAULT_SENDER_EMAIL')
    default_sender_name = os.getenv('MAIL_DEFAULT_SENDER_NAME')
    if default_sender_name and default_sender_email:
        app.config['MAIL_DEFAULT_SENDER'] = (default_sender_name, default_sender_email)
    elif default_sender_email:
        app.config['MAIL_DEFAULT_SENDER'] = default_sender_email
    else:
        app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME') # Fallback

    # Custom config for sender name in email bodies (if different from default sender name part)
    app.config['MAIL_SENDER_NAME'] = os.getenv('MAIL_SENDER_NAME', 'Padre Garcia Polytechnic College')

    # Admin email for receiving contact form submissions
    app.config['ADMIN_EMAIL'] = os.getenv('ADMIN_EMAIL') # ADD THIS LINE


    # --- URL Generation for Email Links ---
    # SERVER_NAME is crucial for url_for(_external=True) to work correctly
    app.config['SERVER_NAME'] = os.getenv('FLASK_SERVER_NAME') 
    app.config['PREFERRED_URL_SCHEME'] = os.getenv('FLASK_PREFERRED_URL_SCHEME', 'http')
    # For url_for to work without an active request context (e.g., in a background task if you add one)
    # app.config['APPLICATION_ROOT'] = '/'
    # app.config['SESSION_COOKIE_DOMAIN'] = os.getenv('FLASK_SERVER_NAME').split(':')[0] if os.getenv('FLASK_SERVER_NAME') else None


    # Initialize extensions
    mail.init_app(app)

    # --- Blueprints ---
    from .views import views # Assuming your views.py is in the same directory (e.g., website/views.py)
    from .auth import auth   # Assuming your auth.py is in the same directory (e.g., website/auth.py)

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/') # Or '/auth' if you prefer

    return app

if __name__ == '__main__':
    # This part is usually for running directly with `python main.py`
    # If using `flask run`, it uses the app factory pattern (create_app)
    app_instance = create_app()
    app_instance.run(host='0.0.0.0', port=5000)