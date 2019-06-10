import os

# uncomment the line below for postgres database url from environment variable
# postgres_local_base = os.environ['DATABASE_URL']

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'my_precious_secret_key')
    DEBUG = False


class DevelopmentConfig(Config):
    # uncomment the line below to use postgres
    # SQLALCHEMY_DATABASE_URI = postgres_local_base
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'flask_boilerplate_main.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    USER_SCRIPT_ROOT = 'robot_user_scripts'
    BACKING_SCRIPT_ROOT = 'robot_backing_scripts'
    TEST_RESULT_ROOT = 'static/results'
    USERS_ROOT = 'static/users'
    UPLOAD_ROOT = 'upload'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.abc.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'abc@123.com'
    SMTP_PASSWORD = '12345678'
    FROM_ADDR = 'Auto Test Admin <abc@123.com>'
    SMTP_ALWAYS_CC = 'ccc@123.com'


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'flask_boilerplate_test.db')
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class ProductionConfig(Config):
    DEBUG = False
    # uncomment the line below to use postgres
    # SQLALCHEMY_DATABASE_URI = postgres_local_base
    USER_SCRIPT_ROOT = 'robot_user_scripts'
    BACKING_SCRIPT_ROOT = 'robot_backing_scripts'
    TEST_RESULT_ROOT = 'static/results'
    USERS_ROOT = 'static/users'
    UPLOAD_ROOT = 'upload'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.abc.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'abc@123.com'
    SMTP_PASSWORD = '12345678'
    FROM_ADDR = 'Auto Test Admin <abc@123.com>'
    SMTP_ALWAYS_CC = 'ccc@123.com'


config_by_name = dict(
    dev=DevelopmentConfig,
    test=TestingConfig,
    prod=ProductionConfig
)

key = Config.SECRET_KEY

def get_config():
    return config_by_name[os.getenv('BOILERPLATE_ENV') or 'dev']
