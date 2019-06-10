from flask import request
from flask_restplus import Resource

from app.main.service.auth_helper import Auth
from app.main.model.database import *
from ..util.dto import AuthDto
from task_runner.runner import start_threads

api = AuthDto.api
user_auth = AuthDto.user_auth


@api.route('/login')
class UserLogin(Resource):
    """
        User Login Resource
    """
    @api.doc('user login')
    @api.expect(user_auth, validate=True)
    def post(self):
        # get the post data
        post_data = request.json
        user = User.objects(email=post_data.get('email')).first()
        for organization in user.organizations:
            start_threads(organization=organization)
            for team in user.teams:
                start_threads(organization=organization, team=team)
        return Auth.login_user(data=post_data)


@api.route('/logout')
class LogoutAPI(Resource):
    """
    Logout Resource
    """
    @api.doc('logout a user')
    def post(self):
        # get auth token
        auth_header = request.headers.get('X-Token')
        return Auth.logout_user(data=auth_header)
