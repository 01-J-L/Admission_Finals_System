import os
from main import app
from flask import Flask

from whitenoise import WhiteNoise

application = WhiteNoise(app)
app = Flask(__name__, static_folder='static')


static_files_directory = os.path.join(app.root_path, app.static_folder)
application.add_files(static_files_directory, prefix=app.static_url_path)

if __name__ == '__main__':
  port = int(os.environ.get("PORT", 4000))
  app.run(host="0.0.0.0", port=port)
