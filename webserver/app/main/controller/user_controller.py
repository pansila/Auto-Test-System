import os
import shutil
from pathlib import Path
from flask import request, send_from_directory
from flask_restx import Resource
from mongoengine import ValidationError

from ..service.auth_helper import Auth
from ..util.decorator import admin_token_required, token_required
from ..model.database import User, Test, TestResult, TaskQueue, Task, Organization, Team

from ..service.user_service import get_all_users, save_new_user
from ..service.auth_helper import Auth
from ..util.dto import UserDto
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, USER_NOT_EXIST, TOKEN_EXPIRED, TOKEN_ILLEGAL, TOKEN_REQUIRED, USER_ALREADY_EXIST, UNKNOWN_ERROR
from ..config import get_config
from ..util.identicon import render_identicon

USERS_ROOT = Path(get_config().USERS_ROOT)

api = UserDto.api
_user = UserDto.user
_user_info_resp = UserDto.user_info_resp
_avatar = UserDto.avatar
_password = UserDto.password
_password_update = UserDto.password_update
_account = UserDto.account


@api.route('/')
class UserList(Resource):
    @api.doc('list_of_registered_users')
    @api.marshal_list_with(_user, envelope='data')
    @admin_token_required
    def get(self):
        """List all registered users"""
        return get_all_users()

    @api.expect(_account)
    @api.response(201, 'User successfully created.')
    @api.doc('create_a_new_user')
    def post(self):
        """Creates a new User"""
        data = request.json
        return save_new_user(data=data)


@api.route('/info')
class UserInfo(Resource):
    @api.doc('get_user_info')
    @api.marshal_with(_user_info_resp)
    def get(self):
        """Get user information"""
        return Auth.get_logged_in_user(request.headers.get('X-Token'))

@api.route('/avatar')
class UserInfo(Resource):
    @api.doc('get_the_avatar')
    def get(self):
        """Get the avatar of a user"""
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    return send_from_directory(Path(os.getcwd()) / USERS_ROOT / user.email, user.avatar)
                return response_message(USER_NOT_EXIST), 401
            return response_message(TOKEN_ILLEGAL, payload), 401
        return response_message(TOKEN_REQUIRED), 400

    @api.doc('upload_the_avatar')
    @token_required
    def post(self, **kwargs):
        """
        Upload the avatar for a user
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        for name, file in request.files.items():
            # ext = file.filename.rpartition('.')[2]
            filename = USERS_ROOT / user.email / 'temp.png'
            file.save(str(filename))

    @api.doc('change_avatar_type')
    @api.expect(_avatar)
    @token_required
    def patch(self, **kwargs):
        """
        Change the avatar type

        type: {custom | default}, where custom means using a custom avatar uploaded by user,
        default means use an identicon generated from user's email
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        avatar_type = request.json.get('type', None)
        if not avatar_type:
            return response_message(EINVAL, 'Field type is required'), 401

        if avatar_type == 'custom':
            filename1 = USERS_ROOT / user.email / 'temp.png'
            if not os.path.exists(filename1):
                return response_message(ENOENT, 'Avatar file not found'), 404

            filename2 = USERS_ROOT / user.email / (str(user.id) + '.png')
            try:
                os.remove(filename2)
            except FileNotFoundError:
                pass

            os.rename(filename1, filename2)
        elif avatar_type == 'default':
            filename = USERS_ROOT / user.email / (str(user.id) + '.png')
            try:
                os.remove(filename)
            except FileNotFoundError:
                pass

            img = render_identicon(hash(user.email), 27)
            img.save(USERS_ROOT / user.email / ('%s.png' % user.id))
        else:
            return response_message(EINVAL, 'Unknown avatar type'), 401

@api.route('/check')
class UserInfoCheck(Resource):
    @api.doc('Check_user_information')
    @api.param('email', description='The email address to check')
    def get(self):
        """Check user information when registering"""
        email = request.args.get('email', None)
        if email:
            user = User.objects(email=email).first()
            if user:
                return response_message(USER_ALREADY_EXIST), 401
            return response_message(SUCCESS)
        else:
            return response_message(UNKNOWN_ERROR, 'No query data found'), 401

@api.route('/account')
class UserAccount(Resource):
    @api.doc('update_user_account')
    @api.expect(_account)
    @token_required
    def post(self, **kwargs):
        """Update the user account information"""
        data = request.json

        user_id = kwargs['user']['user_id']

        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        username = data.get('name', None)
        if username:
            user.name = username

        email = data.get('email', None)
        if email:
            user.email = email

        introduction = data.get('introduction', None)
        if introduction:
            user.introduction = introduction

        region = data.get('region', None)
        if region:
            user.region = region

        try:
            user.save()
        except ValidationError:
            return response_message(EINVAL, 'Failed to update the user account'), 401

    @api.doc('delete_user_account')
    @api.expect(_password)
    @token_required
    def delete(self, **kwargs):
        """Delete the user account"""
        data = request.json

        user_id = kwargs['user']['user_id']

        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        password = data.get('password', None)
        if not password:
            return response_message(EINVAL, 'Field password is required'), 401

        ret = user.check_password(password)
        if not ret:
            return response_message(EINVAL, 'Password is incorrect'), 403

        for org in user.organizations:
            org.modify(pull__members=user)
        for team in user.teams:
            team.modify(pull__members=user)

        user_dir = USERS_ROOT / user.email
        try:
            shutil.rmtree(user_dir)
        except FileNotFoundError:
            pass

        organizations = Organization.objects(owner=user)
        teams = Team.objects(owner=user)

        for org in organizations:
            try:
                shutil.rmtree(USERS_ROOT / org.path)
            except FileNotFoundError:
                pass

            User.objects.update(pull__organizations=org)

            tests = Test.objects(organization=org)
            for test in tests:
                tasks = Task.objects(test=test)
                for task in tasks:
                    TestResult.objects(task=task).delete()
                tasks.delete()
            tests.delete()
            TaskQueue.objects(organization=org).update(to_delete=True, organization=None, team=None)
            org.delete()

        for team in teams:
            User.objects.update(pull__teams=team)
            team.delete()

        user.delete()

        auth_header = request.headers.get('X-Token')
        return Auth.logout_user(data=auth_header)


@api.route('/password')
class UserAccount(Resource):
    @api.doc('update_user_password')
    @api.expect(_password_update)
    @token_required
    def post(self, **kwargs):
        """Update the user password"""
        data = request.json

        user_id = kwargs['user']['user_id']

        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        oldPassword = data.get('oldPassword', None)
        if not oldPassword:
            return response_message(EINVAL, 'Field oldPassword is required'), 401

        newPassword = data.get('newPassword', None)
        if not newPassword:
            return response_message(EINVAL, 'Field newPassword is required'), 401

        ret = user.check_password(oldPassword)
        if not ret:
            return response_message(EINVAL, 'Old password is incorrect'), 403

        user.password = newPassword
        try:
            user.save()
        except ValidationError:
            return response_message(EINVAL, 'Failed to update the user account'), 401
