import aiofiles
import asyncio
import base64
import os
from async_files.utils import async_wraps
from bson import ObjectId
from marshmallow.exceptions import ValidationError
from pathlib import Path

from sanic.log import logger
from sanic.response import json, file
from sanic_openapi import doc
from sanic import Blueprint
from sanic.views import HTTPMethodView

from ..service.auth_helper import Auth
from ..util.decorator import admin_token_required, token_required
from ..model.database import User, Test, TestResult, TaskQueue, Task, Organization, Team

from ..service.user_service import get_all_users, save_new_user
from ..service.auth_helper import Auth
from ..util import async_rmtree, async_exists
from ..util.dto import UserDto, json_response
from ..util.response import response_message, EINVAL, ENOENT, EACCES, SUCCESS, USER_NOT_EXIST, TOKEN_EXPIRED, TOKEN_ILLEGAL, TOKEN_REQUIRED, USER_ALREADY_EXIST, UNKNOWN_ERROR, PASSWORD_INCORRECT
from ..util.identicon import render_identicon
from ..util.get_path import USERS_ROOT

_user_list = UserDto.user_list
_avatar = UserDto.avatar
_password = UserDto.password
_password_update = UserDto.password_update
_account = UserDto.account
_user_info = UserDto.user_info
_user_avatar = UserDto.user_avatar

bp = Blueprint('user', url_prefix='/user')

class UserView(HTTPMethodView):
    @doc.summary('return the list of all registered users')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.produces(_user_list)
    @admin_token_required
    async def get(self, request):
        return json(response_message(SUCCESS, users=await get_all_users()))

    @doc.summary('create a new user')
    @doc.consumes(_account, location='body')
    @doc.produces(json_response)
    async def post(self, request):
        data = request.json
        return json(await save_new_user(data=data))


@bp.get('/info')
@doc.summary('get the user info')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(_user_info)
async def handler(request):
    return json(await Auth.get_logged_in_user(request.headers.get('X-Token')))

class AvatarView(HTTPMethodView):
    @doc.summary('get the user\'s avatar')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.produces(_user_avatar)
    @token_required
    async def get(self, request):
        user = request.ctx.user

        if not await async_exists(USERS_ROOT / user.email / user.avatar):
            return json(response_message(ENOENT))

        async with aiofiles.open(USERS_ROOT / user.email / user.avatar, 'rb') as img:
            _, ext = os.path.splitext(user.avatar)
            return json(response_message(SUCCESS, type=f'image/{ext[1:]}', data=base64.b64encode(await img.read()).decode('ascii')))

    @doc.summary('upload the avatar for a user')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(doc.File(name='file'), location='formData', content_type="multipart/form-data")
    @doc.produces(json_response)
    @token_required
    async def post(self, request):
        user = request.ctx.user

        avatar = request.files.get('file')
        async with aiofiles.open(USERS_ROOT / user.email / 'temp.png', 'wb') as f:
            await f.write(avatar.body)

        return json(response_message(SUCCESS))

    @doc.summary('change the avatar\'s source')
    @doc.description('type: {custom | default}, where "custom" means using a custom avatar uploaded by user, "default" means use an identicon generated from user\'s email')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_avatar, location='body')
    @doc.produces(json_response)
    @token_required
    async def patch(self, request):
        user = request.ctx.user

        avatar_type = request.json.get('type', None)
        if not avatar_type:
            return json(response_message(EINVAL, 'Field type is required'))

        if avatar_type == 'custom':
            filename1 = USERS_ROOT / user.email / 'temp.png'
            if not await async_exists(filename1):
                return json(response_message(ENOENT, 'Avatar file not found'))

            filename2 = USERS_ROOT / user.email / (str(user.pk) + '.png')
            try:
                await aiofiles.os.remove(filename2)
            except FileNotFoundError:
                pass

            await aiofiles.os.rename(filename1, filename2)
        elif avatar_type == 'default':
            filename = USERS_ROOT / user.email / (str(user.pk) + '.png')
            try:
                await aiofiles.os.remove(filename)
            except FileNotFoundError:
                pass

            img = await render_identicon(hash(user.email), 27)
            await async_wraps(img.save)(USERS_ROOT / user.email / f'{user.pk}.png')
        else:
            return json(response_message(EINVAL, 'Unknown avatar type'))
        return json(response_message(SUCCESS))

@bp.get('/check')
@doc.summary('check whether the user exists')
@doc.consumes(doc.String(name="email"))
@doc.produces(json_response)
async def handler(request):
    email = request.args.get('email', None)
    if email:
        user = await User.find_one({'email': email})
        if user:
            return json(response_message(USER_ALREADY_EXIST))
        return json(response_message(USER_NOT_EXIST))
    return json(response_message(EINVAL, 'Field email is required'))

class UserAccountView(HTTPMethodView):
    @doc.summary('update the user account information')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_account, location='body')
    @doc.produces(json_response)
    @token_required
    async def post(self, request):
        data = request.json

        user = request.ctx.user

        username = data.get('name', None)
        if username:
            user.name = username

        email = data.get('email', None)
        if email and email != user.email:
            u = await User.find_one({'email': email})
            if u:
                return json(response_message(USER_ALREADY_EXIST, 'email has been registered'))
            try:
                user.email = email
            except ValidationError as e:
                return json(response_message(EINVAL, str(e)))

        introduction = data.get('introduction', None)
        if introduction:
            user.introduction = introduction

        region = data.get('region', None)
        if region:
            user.region = region

        await user.commit()

        return json(response_message(SUCCESS))

    @doc.summary('delete the user account')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_password, location='body')
    @doc.produces(json_response)
    @token_required
    async def delete(self, request):
        data = request.json

        user = request.ctx.user

        password = data.get('password', None)
        if not password:
            return json(response_message(EINVAL, 'Field password is required'))

        ret = user.check_password(password)
        if not ret:
            return json(response_message(PASSWORD_INCORRECT))

        for organization in user.organizations:
            org = await organization.fetch()
            org.members.remove(user)
            await org.commit()
        if user.teams:
            for team in user.teams:
                t = await team.fetch()
                t.members.remove(user)
                await team.commit()

        user_dir = USERS_ROOT / user.email
        if await async_exists(user_dir):
            await async_rmtree(user_dir)

        async for team in Team.find({'owner': user.pk}):
            if len(team.members) > 1: # and team.members[0] == user
                return json(response_message(EACCES, 'you have owned a team, please transfer the ownership to another member first'))
        async for org in Organization.find({'owner': user.pk}):
            if len(org.members) > 1: # and org.members[0] == user
                return json(response_message(EACCES, 'you have owned an organization, please transfer the ownership to another member first'))

        async for team in Team.find({'owner': user.pk}):
            async for u in User.find():
                u.teams.remove(team)
                await u.commit()
            await team.delete()

        async for org in Organization.find({'owner': user.pk}):
            org_path = USERS_ROOT / org.path
            if await async_exists(org_path):
                await async_rmtree(org_path)

            async for u in User.find():
                # if org.pk in u.organizations:
                u.organizations.remove(org)
                await u.commit()

            async for test in Test.find({'organization': org.pk}):
                async for task in Task.find({'test': test}):
                    async for tr in TestResult.find({'task': task.pk}):
                        await tr.delete()
                    await task.delete()
                await test.delete()
            async for queue in TaskQueue.find({'organization': org.pk}):
                await queue.update({'to_delete': True, 'organization': None, 'team': None})
            await org.delete()

        await user.delete()

        auth_header = request.headers.get('X-Token')
        return json(await Auth.logout_user(data=auth_header))


@bp.post('/password')
@doc.summary('update the user password')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_password_update, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    data = request.json

    user = request.ctx.user

    oldPassword = data.get('oldPassword', None)
    if not oldPassword:
        return json(response_message(EINVAL, 'Field oldPassword is required'))

    newPassword = data.get('newPassword', None)
    if not newPassword:
        return json(response_message(EINVAL, 'Field newPassword is required'))

    ret = user.check_password(oldPassword)
    if not ret:
        return json(response_message(EINVAL, 'Old password is incorrect'))

    user.password = newPassword
    await user.commit()

    return json(response_message(SUCCESS))

bp.add_route(UserView.as_view(), '/')
bp.add_route(UserAccountView.as_view(), '/account')
bp.add_route(AvatarView.as_view(), '/avatar')
