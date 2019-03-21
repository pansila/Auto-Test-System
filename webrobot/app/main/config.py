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
    SCRIPT_ROOT = '../example-test-scripts/robot_backing_scripts'
    TEST_RESULT_ROOT = 'static/results'
    UPLOAD_ROOT = 'upload'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'autotest'
    SMTP_SERVER = 'smtp.qiye.aliyun.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'ftsw@freethink.cn'
    SMTP_PASSWORD = 'freethink_123'
    FROM_ADDR = 'Auto Test Admin <ftsw@freethink.cn>'
    SMTP_ALWAYS_CC = 'lin.zhou@freethink.cn'


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
    SCRIPT_ROOT = '../example-test-scripts/robot_backing_scripts'
    TEST_RESULT_ROOT = 'static/results'
    UPLOAD_ROOT = 'upload'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'autotest'
    SMTP_SERVER = 'smtp.qiye.aliyun.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'ftsw@freethink.cn'
    SMTP_PASSWORD = 'freethink_123'
    FROM_ADDR = 'Auto Test Admin <ftsw@freethink.cn>'
    SMTP_ALWAYS_CC = 'lin.zhou@freethink.cn'


config_by_name = dict(
    dev=DevelopmentConfig,
    test=TestingConfig,
    prod=ProductionConfig
)

key = Config.SECRET_KEY

def get_config():
    return config_by_name[os.getenv('BOILERPLATE_ENV') or 'dev']
