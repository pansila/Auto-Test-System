import os
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource

from app.main.util.decorator import admin_token_required, token_required
from app.main.model.database import User, Organization, Team

from ..util.dto import TeamDto
from ..util.errors import *
from ..config import get_config

USERS_ROOT = Path(get_config().USERS_ROOT)

api = TeamDto.api
_team = TeamDto.team


@api.route('/')
class UserList(Resource):
    @api.doc('List all teams associated with the user')
    @token_required
    def get(self):
        pass

    @token_required
    @api.response(201, 'Team successfully created.')
    @api.doc('create a new team')
    def post(self):
        pass

