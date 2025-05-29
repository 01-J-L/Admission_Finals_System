from website import create_app
from dotenv import load_dotenv
import os
load_dotenv() 

app = create_app()



if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)


