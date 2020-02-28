
from app.main import db

from app.main.model.database import BlacklistToken
from flask import current_app

from ..util.errors import *

def save_token(token):
    blacklist_token = BlacklistToken(token=token)
    try:
        # insert the token
        blacklist_token.save()
        return error_message(SUCCESS), 200
    except Exception as e:
        current_app.logger.exception(e)
        return error_message(UNKNOWN_ERROR), 401
