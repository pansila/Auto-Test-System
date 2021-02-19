import os
import logging
from pathlib import Path
from sanic.log import logger
from logging.handlers import RotatingFileHandler

# uncomment the line below for postgres database url from environment variable
# postgres_local_base = os.environ['DATABASE_URL']

basedir = os.path.abspath(Path(os.path.dirname(__file__)) / '../../')

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'my_precious_secret_key')
    SSL_DISABLE = False
    SQLALCHEMY_RECORD_QUERIES = True
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True
    UPLOAD_ROOT = 'static/upload'
    USERS_ROOT = 'static/users'
    STORE_ROOT = 'static/pypi'
    DOCUMENT_ROOT = 'static/document'
    PICTURE_ROOT = 'static/pictures'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.abc.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'abc@123.com'
    SMTP_PASSWORD = '12345678'
    FROM_ADDR = 'Auto Test Admin <abc@123.com>'
    SMTP_ALWAYS_CC = 'ccc@123.com'
    API_SECURITY = [{"ApiKeyAuth": []}]
    API_SECURITY_DEFINITIONS = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-TOKEN"}
    }


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    UPLOAD_ROOT = 'test/upload'
    USERS_ROOT = 'test/users'
    STORE_ROOT = 'test/pypi'
    DOCUMENT_ROOT = 'test/document'
    PICTURE_ROOT = 'test/pictures'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'test_auto_test'
    SMTP_SERVER = 'smtp.abc.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'abc@123.com'
    SMTP_PASSWORD = '12345678'
    FROM_ADDR = 'Auto Test Admin <abc@123.com>'
    SMTP_ALWAYS_CC = 'ccc@123.com'
    API_SECURITY = [{"ApiKeyAuth": []}]
    API_SECURITY_DEFINITIONS = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-TOKEN"}
    }


class ProductionConfig(Config):
    DEBUG = False
    UPLOAD_ROOT = 'upload'
    USERS_ROOT = 'static/users'
    STORE_ROOT = 'static/pypi'
    DOCUMENT_ROOT = 'static/document'
    PICTURE_ROOT = 'static/pictures'
    MONGODB_URL = '127.0.0.1'
    MONGODB_PORT = 27017
    MONGODB_DATABASE = 'auto_test'
    SMTP_SERVER = 'smtp.abc.com'
    SMTP_SERVER_PORT = 25
    SMTP_USER = 'abc@123.com'
    SMTP_PASSWORD = '12345678'
    FROM_ADDR = 'Auto Test Admin <abc@123.com>'
    SMTP_ALWAYS_CC = 'ccc@123.com'
    API_SECURITY = [{"ApiKeyAuth": []}]
    API_SECURITY_DEFINITIONS = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-TOKEN"}
    }


config_by_name = dict(
    dev=DevelopmentConfig,
    test=TestingConfig,
    prod=ProductionConfig
)

key = Config.SECRET_KEY


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

def setup_logger():
    LOG_PATH = os.path.join(basedir, 'logs')
    LOG_PATH_ERROR = os.path.join(LOG_PATH, 'error.log')
    LOG_PATH_INFO = os.path.join(LOG_PATH, 'info.log')
    LOG_FILE_MAX_BYTES = 100 * 1024 * 1024
    LOG_FILE_BACKUP_COUNT = 10

    try:
        os.mkdir(LOG_PATH)
    except FileExistsError:
        pass

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(process)d %(thread)d '
        '%(pathname)s %(lineno)s %(message)s')


    # FileHandler Info
    file_handler_info = RotatingFileHandler(filename=LOG_PATH_INFO, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT)
    file_handler_info.setFormatter(formatter)
    file_handler_info.setLevel(logging.INFO)
    info_filter = InfoFilter()
    file_handler_info.addFilter(info_filter)
    logger.addHandler(file_handler_info)

    # FileHandler Error
    file_handler_error = RotatingFileHandler(filename=LOG_PATH_ERROR, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT)
    file_handler_error.setFormatter(formatter)
    file_handler_error.setLevel(logging.ERROR)
    logger.addHandler(file_handler_error)

def get_config():
    return config_by_name[os.getenv('BOILERPLATE_ENV') or 'dev']

setup_logger()
