import os
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource

from app.main.util.decorator import admin_token_required, token_required
from app.main.model.database import User

from ..service.user_service import get_a_user, get_all_users, save_new_user
from ..service.auth_helper import Auth
from ..util.dto import UserDto
from ..util.errors import *
from ..config import get_config

USERS_ROOT = Path(get_config().USERS_ROOT)

api = UserDto.api
_user = UserDto.user


@api.route('/')
class UserList(Resource):
    @api.doc('list_of_registered_users')
    @admin_token_required
    @api.marshal_list_with(_user, envelope='data')
    def get(self):
        """List all registered users"""
        return get_all_users()

    @api.expect(_user, validate=True)
    @api.response(201, 'User successfully created.')
    @api.doc('create a new user')
    def post(self):
        """Creates a new User """
        data = request.json
        return save_new_user(data=data)


@api.route('/info')
class UserInfo(Resource):
    """
    User information
    """
    @api.doc('get the information of a user')
    def get(self):
        return Auth.get_logged_in_user(request)

@api.route('/avatar')
class UserInfo(Resource):
    """
    User avatar
    """
    @api.doc('get the avatar of a user')
    def get(self):
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    return send_from_directory(Path(os.getcwd()) / USERS_ROOT / user.email, user.avatar)
                else:
                    return error_message(USER_NOT_EXIST), 401

        return error_message(TOKEN_ILLEGAL), 401

@api.route('/check')
class UserInfoCheck(Resource):
    """
    Check User information for register
    """
    @api.doc('Check User information for register')
    def get(self):
        email = request.args.get('email', None)
        if email:
            user = User.objects(email=email).first()
            if user:
                return error_message(USER_ALREADY_EXIST), 401
            return error_message(SUCCESS), 200
        else:
            return error_message(UNKNOWN_ERROR, 'No query data found'), 401
