from app.main.model.database import User
from flask import current_app
from ..service.blacklist_service import save_token
from ..util.errors import *


class Auth:

    @staticmethod
    def login_user(data):
        try:
            # fetch the user data
            user = User.objects(email=data.get('email')).first()
            if user:
                if user.check_password(data.get('password')):
                    auth_token = User.encode_auth_token(str(user.id))
                    if auth_token:
                        return error_message(SUCCESS, token=auth_token.decode()), 200
                    return error_message(UNKNOWN_ERROR), 401
                return error_message(PASSWORD_INCORRECT), 401
            return error_message(USER_NOT_EXIST), 404
        except Exception as e:
            current_app.logger.exception(e)
            return error_message(EAGAIN), 500

    @staticmethod
    def logout_user(data):
        auth_token = data if data else ''
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                # mark the token as blacklisted
                return save_token(token=auth_token)
            return error_message(TOKEN_ILLEGAL, payload), 401
        return error_message(TOKEN_REQUIRED), 401

    @staticmethod
    def get_logged_in_user(new_request):
        # get the auth token
        auth_token = new_request.headers.get('X-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    return error_message(SUCCESS,
                            user_id=str(user.id),
                            email=user.email,
                            username=user.name,
                            roles=user.roles,
                            registered_on=user.registered_on,
                            avatar=user.avatar,
                            introduction=user.introduction,
                            region=user.region
                        ), 200
                return error_message(USER_NOT_EXIST), 404
            return error_message(TOKEN_ILLEGAL, payload), 401
        return error_message(TOKEN_REQUIRED), 401
