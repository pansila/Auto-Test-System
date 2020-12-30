# import uuid
import asyncio
import aiofiles
import datetime
import os
from async_files.utils import async_wraps
from bson import ObjectId
from pathlib import Path

from sanic.log import logger
from sanic.response import json

from app.main.model.database import User, Organization
from ..config import get_config
from ..util.response import *
from ..util.identicon import render_identicon

USERS_ROOT = Path(get_config().USERS_ROOT)

async def save_new_user(data, admin=None):
    user = await User.find_one({'email': data['email']})
    if not user:
        new_user = User(
            # public_id=str(uuid.uuid4()),
            email=data['email'],
            name=data.get('username', ''),
            registered_on=datetime.datetime.utcnow(),
            avatar=data.get('avatar', ''),
            introduction=data.get('introduction', '')
        )
        cnt = await User.count_documents()
        if cnt == 0:
            new_user.roles = ['admin']
        else:
            new_user.roles = ['viewer']
        new_user.password = data['password']
        try:
            await new_user.commit()
        except Exception as e:
            logger.exception(e)
            return response_message(EINVAL, 'Field validating for User failed')

        user_root = USERS_ROOT / data['email']
        try:
            await aiofiles.os.mkdir(user_root)
        except FileExistsError as e:
            return response_message(EEXIST)
        try:
            await aiofiles.os.mkdir(user_root / 'test_results')
        except FileExistsError as e:
            return response_message(EEXIST)

        if new_user.avatar == '':
            img = await render_identicon(hash(data['email']), 27)
            await async_wraps(img.save)(user_root / ('%s.png' % new_user.pk))
            new_user.avatar = '%s.png' % new_user.pk
        if new_user.name == '':
            new_user.name = new_user.email.split('@')[0]
        if not admin:
            organization = Organization(name='Personal')
            organization.owner = new_user
            organization.path = new_user.email
            organization.members = [new_user]
            organization.personal = True
            await organization.commit()
            new_user.organizations = [organization]
        await new_user.commit()

        return generate_token(new_user)
    else:
        return response_message(USER_ALREADY_EXIST)


async def get_all_users():
    return await User.find().to_list()


async def get_a_user(user_id):
    return await User.find_one({'_id': ObjectId(user_id)})


def generate_token(user):
    try:
        # generate the auth token
        auth_token = User.encode_auth_token(str(user.pk))
        return response_message(SUCCESS, token=auth_token.decode())
    except Exception as e:
        logger.exception(e)
        return response_message(UNKNOWN_ERROR)

