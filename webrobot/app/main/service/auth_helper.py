from app.main.model.database import User
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
                        response_object = {
                            'code': SUCCESS,
                            'data': {
                                'message': 'Successfully logged in.',
                                'token': auth_token.decode()
                            }
                        }
                        return response_object, 200
                    else:
                        response_object = {
                            'code': UNKNOWN_ERROR,
                            'data': {
                                'message': 'Some error happened.'
                            }
                        }
                        return response_object, 401
                else:
                    response_object = {
                        'code': PASSWORD_INCORRECT,
                        'data': {
                            'message': 'password does not match.'
                        }
                    }
                    return response_object, 401
            else:
                response_object = {
                    'code': USER_NOT_EXIST,
                    'data': {
                        'message': 'email does not exist.'
                    }
                }
                return response_object, 401

        except Exception as e:
            print(e)
            response_object = {
                'code': UNKNOWN_ERROR,
                'data': {
                    'message': 'Try again'
                }
            }
            return response_object, 500

    @staticmethod
    def logout_user(data):
        auth_token = data if data else ''
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                # mark the token as blacklisted
                return save_token(token=auth_token)
            else:
                response_object = {
                    'code': UNKNOWN_ERROR,
                    'data': {
                        'message': payload
                    }
                }
                return response_object, 401
        else:
            response_object = {
                'code': TOKEN_ILLEGAL,
                'data': {
                    'message': 'Provide a valid auth token.'
                }
            }
            return response_object, 403

    @staticmethod
    def get_logged_in_user(new_request):
        # get the auth token
        auth_token = new_request.headers.get('X-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                response_object = {
                    'code': SUCCESS,
                    'data': {
                        'user_id': str(user.id),
                        'email': user.email,
                        'roles': user.roles,
                        'registered_on': str(user.registered_on),
                        'avatar': user.avatar,
                        'introduction': user.introduction
                    }
                }
                return response_object, 200
            response_object = {
                'code': TOKEN_ILLEGAL,
                'data': {
                    'message': payload
                }
            }
            return response_object, 401
        else:
            response_object = {
                'code': TOKEN_REQUIRED,
                'data': {
                    'message': 'Provide a valid auth token.'
                }
            }
            return response_object, 401
