from flask import Flask
from flask_bcrypt import Bcrypt

from .config import config_by_name

flask_bcrypt = Bcrypt()


def create_app(config_name):
    app = Flask(__name__,
            static_url_path='',
            static_folder='../../static',
            template_folder='../../templates')
    app.config.from_object(config_by_name[config_name])
    flask_bcrypt.init_app(app)

    return app