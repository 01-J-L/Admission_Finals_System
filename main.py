from website import create_app
from dotenv import load_dotenv
load_dotenv() 

from flask import Flask
app = Flask(__name__, static_folder='static')


app = create_app()





