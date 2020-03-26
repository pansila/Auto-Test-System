from app.main.model.database import User
from flask import current_app
from ..service.blacklist_service import save_token
from ..util.response import *


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
                        return response_message(SUCCESS, token=auth_token.decode()), 200
                    return response_message(UNKNOWN_ERROR), 401
                return response_message(PASSWORD_INCORRECT), 401
            return response_message(USER_NOT_EXIST), 404
        except Exception as e:
            current_app.logger.exception(e)
            return response_message(EAGAIN), 500

    @staticmethod
    def logout_user(data):
        auth_token = data if data else ''
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                # mark the token as blacklisted
                return save_token(token=auth_token)
            return response_message(TOKEN_ILLEGAL, payload), 401
        return response_message(TOKEN_REQUIRED), 401

    @staticmethod
    def get_logged_in_user(token):
        if token:
            payload = User.decode_auth_token(token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    return response_message(SUCCESS,
                            user_id=str(user.id),
                            email=user.email,
                            username=user.name,
                            roles=user.roles,
                            registered_on=user.registered_on,
                            avatar=user.avatar,
                            introduction=user.introduction,
                            region=user.region
                        ), 200
                return response_message(USER_NOT_EXIST), 404
            return response_message(TOKEN_ILLEGAL, payload), 401
        return response_message(TOKEN_REQUIRED), 401

    @staticmethod
    def is_user_authenticated(token):
        resp = Auth.get_logged_in_user(token)
        if resp[0]['code'] == SUCCESS[0]:
            return True
        return False