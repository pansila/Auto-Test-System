
from app.main.model.database import BlacklistToken
from flask import current_app

from ..util.response import *

def save_token(token):
    blacklist_token = BlacklistToken(token=token)
    try:
        # insert the token
        blacklist_token.save()
        return response_message(SUCCESS)
    except Exception as e:
        current_app.logger.exception(e)
        return response_message(UNKNOWN_ERROR), 401
