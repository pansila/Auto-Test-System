from functools import wraps

from flask import request

from app.main.service.auth_helper import Auth
from ..util.errors import *


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS[0]:
            return data, status

        return f(*args, data['data'], **kwargs)

    return decorated


def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS[0]:
            return data, status

        roles = token.get('roles')
        if 'admin' not in roles:
            return error_message(ADMIN_TOKEN_REQUIRED), 401

        return f(*args, **kwargs)

    return decorated
