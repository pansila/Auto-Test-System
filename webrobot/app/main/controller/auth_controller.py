from flask import request
from flask_restx import Resource

from app.main.service.auth_helper import Auth
from app.main.model.database import *
from ..util.dto import AuthDto
from ..util.response import *
from task_runner.runner import initialize_runner

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
        """
        User login interface
        """
        post_data = request.json
        msg, status = Auth.login_user(data=post_data)
        if status != 200:
            return msg, status

        user = User.objects(email=post_data.get('email')).first()
        initialize_runner(user)

        return msg, status



@api.route('/logout')
class LogoutAPI(Resource):
    """
    Logout Resource
    """
    @api.doc('logout a user')
    def post(self):
        """
        User logout interface
        """
        auth_header = request.headers.get('X-Token')
        return Auth.logout_user(data=auth_header)
