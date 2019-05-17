
from app.main import db

from app.main.model.database import BlacklistToken

from ..util.errors import *

def save_token(token):
    blacklist_token = BlacklistToken(token=token)
    try:
        # insert the token
        blacklist_token.save()
        response_object = {
            'code': SUCCESS,
            'data': {
                'message': 'Successfully logged out.'
            }
        }
        return response_object, 200
    except Exception as e:
        print(e)
        response_object = {
            'code': UNKNOWN_ERROR,
            'data': {
                'message': e
            }
        }
        return response_object, 401
