import os
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource
from bson import ObjectId

from app.main.util.decorator import token_required
from app.main.model.database import *

from ..service.auth_helper import Auth
from ..util.dto import TeamDto
from ..util.errors import *
from ..config import get_config
from ..util.identicon import *

USERS_ROOT = Path(get_config().USERS_ROOT)

api = TeamDto.api
_team = TeamDto.team


@api.route('/')
class TeamList(Resource):
    @token_required
    @api.doc('List all teams associated with the user')
    def get(self, user):
        ret = []
        check = []
        user_id = user['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        teams = Team.objects(owner=ObjectId(user_id))
        for team in teams:
            check.append(team)
            ret.append({
                'label': team.name,
                'owner': team.owner.name,
                'owner_email': team.owner.email,
                'organization_id': str(team.organization.id),
                'value': str(team.id)
            })

        for team in user.teams:
            if team in check:
                continue
            ret.append({
                'label': team.name,
                'owner': team.owner.name,
                'owner_email': team.owner.email,
                'organization_id': str(team.organization.id),
                'value': str(team.id)
            })

        return ret

    @token_required
    @api.response(201, 'Team successfully created.')
    @api.doc('create a new team')
    def post(self, user):
        data = request.json
        name = data.get('name', None)
        if not name:
            return error_message(EINVAL, 'Field name is required'), 400

        organization_id = data.get('organization_id', None)
        if not organization_id:
            return error_message(EINVAL, 'Field organization_id is required'), 400
        
        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return error_message(ENOENT, 'Organization not found'), 404

        team = Team.objects(name=name, organization=organization).first()
        if team:
            return error_message(EEXIST, 'Team has been registered'), 403

        user = User.objects(pk=user['user_id']).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        team = Team(name=name, organization=organization, owner=user)
        team.members.append(user)
        team.save()
        user.teams.append(team)
        user.save()
        organization.teams.append(team)
        organization.save()

        team_root = USERS_ROOT / organization.path / name
        try:
            os.mkdir(team_root)
        except FileExistsError as e:
            return error_message(EEXIST), 401

        img= render_identicon(hash(name), 27)
        img.save(team_root / ('%s.png' % team.id))
        team.avatar = '%s.png' % team.id
        team.save()

@api.route('/avatar/<team_id>')
class TeamAvatar(Resource):
    @api.doc('get the avatar for an team')
    def get(self, team_id):
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    team = Team.objects(pk=team_id).first()
                    if team:
                        return send_from_directory(Path(os.getcwd()) / USERS_ROOT / team.organization.path / team.name, team.avatar)
                    return error_message(USER_NOT_EXIST, 'Team not found'), 404
                return error_message(USER_NOT_EXIST), 404
            return error_message(TOKEN_ILLEGAL, payload), 401
        return error_message(TOKEN_REQUIRED), 400

@api.route('/member')
class TeamMember(Resource):
    @token_required
    @api.doc('remove a member from the team')
    def delete(self, user):
        user_id = user['user_id']
        team_id = request.json.get('team_id', None)
        if not team_id:
            return error_message(EINVAL, "Field team_id is required"), 400

        team_to_quit = Team.objects(pk=team_id).first()
        if not team_to_quit:
            return error_message(ENOENT, "Team not found"), 404

        user = User.objects(pk=user_id).first()
        if not user:
            return error_message(ENOENT, "User not found"), 404

        for team in user.teams:
            if team != team_to_quit:
                continue
            if team.owner == user:
                return error_message(EPERM, "Can't quit the team as you are the owner"), 403
            team.modify(pull__members=user)
            user.modify(pull__teams=team)
            return error_message(SUCCESS), 200
        else:
            return error_message(EINVAL, "User is not in the team"), 400

@api.route('/all')
class TeamListAll(Resource):
    @token_required
    @api.doc('List all teams registered')
    def get(self, user):
        ret = []

        teams = Team.objects(name__not__exact='Personal')
        for team in teams:
            r = {
                'label': team.name,
                'owner': team.owner.name,
                'owner_email': team.owner.email,
                'value': str(team.id)
            }
            ret.append(r)
        return ret

@api.route('/join')
class TeamJoin(Resource):
    @token_required
    @api.doc('join an team')
    def post(self, user):
        team_id = request.json.get('id', None)
        if not team_id:
            return error_message(EINVAL, "Field id is required"), 400

        user = User.objects(pk=user['user_id']).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        team = Team.objects(pk=team_id).first()
        if not team:
            return error_message(ENOENT, 'Team not found'), 404

        if user not in team.members:
            team.modify(push__members=user)
        if team not in user.teams:
            user.modify(push__teams=team)
