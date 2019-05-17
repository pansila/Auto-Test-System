from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

from .config import config_by_name

db = SQLAlchemy()
flask_bcrypt = Bcrypt()


def create_app(config_name):
    app = Flask(__name__,
            static_url_path='',
            static_folder='../../static',
            template_folder='../../templates')
    app.config.from_object(config_by_name[config_name])
    with app.app_context():
        db.init_app(app)
        db.create_all()
    flask_bcrypt.init_app(app)

    return app