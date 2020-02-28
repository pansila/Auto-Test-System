import os
import logging
from pathlib import Path

# uncomment the line below for postgres database url from environment variable
# postgres_local_base = os.environ['DATABASE_URL']

basedir = os.path.abspath(Path(os.path.dirname(__file__)) / '../../')


class InfoFilter(logging.Filter):
    def filter(self, record):
        """only use INFO
        :param record:
        :return:
        """
        if logging.INFO <= record.levelno < logging.ERROR:
            return super().filter(record)
        else:
            return 0
 
 
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'my_precious_secret_key')
    SSL_DISABLE = False
    SQLALCHEMY_RECORD_QUERIES = True
    DEBUG = False
 
    LOG_PATH = os.path.join(basedir, 'logs')
    LOG_PATH_ERROR = os.path.join(LOG_PATH, 'error.log')
    LOG_PATH_INFO = os.path.join(LOG_PATH, 'info.log')
    LOG_FILE_MAX_BYTES = 100 * 1024 * 1024
    LOG_FILE_BACKUP_COUNT = 10
 
    APP = None

    @classmethod
    def init_app(cls, app):
        cls.APP = app
        try:
            os.mkdir(cls.LOG_PATH)
        except FileExistsError:
            pass


class DevelopmentConfig(Config):
    # uncomment the line below to use postgres
    # SQLALCHEMY_DATABASE_URI = postgres_local_base
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'flask_boilerplate_main.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    USERS_ROOT = 'static/users'
    UPLOAD_ROOT = 'upload'
    STORE_ROOT = 'static/test_packages'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.qiye.aliyun.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'ftsw@freethink.cn'
    SMTP_PASSWORD = 'freethink_123'
    FROM_ADDR = 'Auto Test Admin <ftsw@freethink.cn>'
    SMTP_ALWAYS_CC = 'lin.zhou@freethink.cn'

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
 
        # email errors to the administrators
        import logging
        from logging.handlers import RotatingFileHandler
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(process)d %(thread)d '
            '%(pathname)s %(lineno)s %(message)s')
 
 
        # FileHandler Info
        file_handler_info = RotatingFileHandler(filename=cls.LOG_PATH_INFO, maxBytes=cls.LOG_FILE_MAX_BYTES, backupCount=cls.LOG_FILE_BACKUP_COUNT)
        file_handler_info.setFormatter(formatter)
        file_handler_info.setLevel(logging.INFO)
        info_filter = InfoFilter()
        file_handler_info.addFilter(info_filter)
        app.logger.addHandler(file_handler_info)
 
        # FileHandler Error
        file_handler_error = RotatingFileHandler(filename=cls.LOG_PATH_ERROR, maxBytes=cls.LOG_FILE_MAX_BYTES, backupCount=cls.LOG_FILE_BACKUP_COUNT)
        file_handler_error.setFormatter(formatter)
        file_handler_error.setLevel(logging.ERROR)
        app.logger.addHandler(file_handler_error)

    @classmethod
    def logger(cls):
        return cls.APP.logger

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
    USERS_ROOT = 'static/users'
    UPLOAD_ROOT = 'upload'
    STORE_ROOT = 'static/test_packages'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.qiye.aliyun.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'ftsw@freethink.cn'
    SMTP_PASSWORD = 'freethink_123'
    FROM_ADDR = 'Auto Test Admin <ftsw@freethink.cn>'
    SMTP_ALWAYS_CC = 'lin.zhou@freethink.cn'

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)
 
        # email errors to the administrators
        import logging
        from logging.handlers import RotatingFileHandler
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s %(process)d %(thread)d '
            '%(pathname)s %(lineno)s %(message)s')
 
 
        # FileHandler Info
        file_handler_info = RotatingFileHandler(filename=cls.LOG_PATH_INFO)
        file_handler_info.setFormatter(formatter)
        file_handler_info.setLevel(logging.INFO)
        info_filter = InfoFilter()
        file_handler_info.addFilter(info_filter)
        app.logger.addHandler(file_handler_info)
 
        # FileHandler Error
        file_handler_error = RotatingFileHandler(filename=cls.LOG_PATH_ERROR)
        file_handler_error.setFormatter(formatter)
        file_handler_error.setLevel(logging.ERROR)
        app.logger.addHandler(file_handler_error)


config_by_name = dict(
    dev=DevelopmentConfig,
    test=TestingConfig,
    prod=ProductionConfig
)

key = Config.SECRET_KEY

def get_config():
    return config_by_name[os.getenv('BOILERPLATE_ENV') or 'dev']
