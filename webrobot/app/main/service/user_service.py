# import uuid
import datetime

from app.main import db
from app.main.model.database import User

from ..util.errors import *

def save_new_user(data):
    user = User.objects(email=data['email']).first()
    if not user:
        new_user = User(
            # public_id=str(uuid.uuid4()),
            email=data['email'],
            username=data['username'],
            registered_on=datetime.datetime.utcnow(),
            roles=data['roles'],
            avatar=data['avatar'],
            introduction=data['introduction']
        )
        new_user.password = data['password']
        new_user.save()
        return generate_token(new_user)
    else:
        response_object = {
            'code': USER_ALREADY_EXIST,
            'data': {
                'message': 'User already exists. Please Log in.',
            }
        }
        return response_object, 409


def get_all_users():
    return User.objects()


def get_a_user(user_id):
    return User.objects(pk=user_id).first()


def generate_token(user):
    try:
        # generate the auth token
        auth_token = User.encode_auth_token(str(user.id))
        response_object = {
            'code': SUCCESS,
            'data': {
                'message': 'Successfully registered.',
                'token': auth_token.decode()
            }
        }
        return response_object, 201
    except Exception as e:
        response_object = {
            'code': UNKNOWN_ERROR,
            'data': {
                'message': 'Some error occurred. Please try again.'
            }
        }
        return response_object, 401

