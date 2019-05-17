from functools import wraps

from flask import request

from app.main.service.auth_helper import Auth
from ..util.errors import *


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS:
            return data, status

        return f(*args, **kwargs)

    return decorated


def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS:
            return data, status

        roles = token.get('roles')
        if 'admin' not in roles:
            response_object = {
                'code': ADMIN_TOKEN_REQUIRED,
                'data': {
                    'message': 'admin token required'
                }
            }
            return response_object, 401

        return f(*args, **kwargs)

    return decorated
