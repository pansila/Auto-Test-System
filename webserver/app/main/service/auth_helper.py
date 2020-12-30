import json
from app import db
from app.main.model.database import User
from sanic.log import logger
from bson import ObjectId, json_util

from ..service.blacklist_service import save_token
from ..util.response import *


class Auth:

    @staticmethod
    async def login_user(data):
        try:
            # fetch the user data
            user = await User.find_one({'email': data.get('email')})
            if user:
                if user.check_password(data.get('password')):
                    auth_token = User.encode_auth_token(str(user.pk))
                    if auth_token:
                        return response_message(SUCCESS, token=auth_token.decode())
                    return response_message(UNKNOWN_ERROR)
                return response_message(PASSWORD_INCORRECT)
            return response_message(USER_NOT_EXIST)
        except Exception as e:
            logger.exception(e)
            return response_message(EAGAIN)

    @staticmethod
    async def logout_user(data):
        auth_token = data
        if auth_token:
            payload = await User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                # mark the token as blacklisted
                return await save_token(token=auth_token)
            return response_message(TOKEN_ILLEGAL, payload)
        return response_message(TOKEN_REQUIRED)

    @staticmethod
    async def get_logged_in_user(token):
        if token:
            payload = await User.decode_auth_token(token)
            if not isinstance(payload, str):
                user = await User.find_one({'_id': ObjectId(payload['sub'])})
                if user:
                    return response_message(SUCCESS,
                            user_id=str(user.pk),
                            email=user.email,
                            username=user.name,
                            roles=user.roles,
                            registered_on=user.registered_on.timestamp() * 1000,
                            avatar=user.avatar,
                            introduction=user.introduction,
                            region=user.region
                        )
                return response_message(USER_NOT_EXIST)
            return response_message(TOKEN_ILLEGAL, payload)
        return response_message(TOKEN_REQUIRED)

    @staticmethod
    async def is_user_authenticated(token):
        ret = await Auth.get_logged_in_user(token)
        if ret['code'] == SUCCESS[0]:
            return True
        return False
