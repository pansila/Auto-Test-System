import os
import shutil
from pathlib import Path
from flask import request, send_from_directory
from flask_restx import Resource
from bson import ObjectId

from app.main.util.decorator import token_required
from app.main.model.database import *

from ..service.auth_helper import Auth
from ..util.dto import TeamDto
from ..util.response import *
from ..config import get_config
from ..util.identicon import *

USERS_ROOT = Path(get_config().USERS_ROOT)

api = TeamDto.api
_user = TeamDto.user
_team = TeamDto.team
_new_team = TeamDto.new_team
_team_id = TeamDto.team_id


@api.route('/')
class TeamList(Resource):
    @token_required
    @api.doc('list all teams')
    @api.marshal_list_with(_team)
    def get(self, **kwargs):
        """List all teams joined by the logged in user"""
        ret = []
        check = []
        user_id = kwargs['user']['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

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
    @api.doc('create a new team')
    @api.expect(_new_team)
    def post(self, **kwargs):
        """
        Create a new team

        Note: The logged in user performing the operation will become the owner of the team
        """
        data = request.json
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        name = data.get('name', None)
        if not name:
            return response_message(EINVAL, 'Field name is required'), 400

        organization_id = data.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, 'Field organization_id is required'), 400
        
        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404

        if organization.owner != user:
            return response_message(EINVAL, 'Your are not the organization\'s owner'), 403

        team = Team.objects(name=name, organization=organization).first()
        if team:
            return response_message(EEXIST, 'Team has been registered'), 403

        team = Team(name=name, organization=organization, owner=user)
        team.members.append(user)
        team.save()
        user.teams.append(team)
        user.save()
        organization.teams.append(team)
        organization.save()

        team.path = name + '#' + str(team.id)
        team_root = USERS_ROOT / organization.path / team.path
        try:
            os.mkdir(team_root)
        except FileExistsError as e:
            return response_message(EEXIST), 401

        img= render_identicon(hash(name), 27)
        img.save(team_root / ('%s.png' % team.id))
        team.avatar = '%s.png' % team.id
        team.save()

    @token_required
    @api.doc('delete a team')
    @api.expect(_team_id)
    def delete(self, **kwargs):
        """
        Delete an team

        Note: Only the owner of the team or the organization that the team belongs to could perform this operation
        """
        team_id = request.json.get('team_id', None)
        if not team_id:
            return response_message(EINVAL, "Field team_id is required"), 400

        team = Team.objects(pk=team_id).first()
        if not team:
            return response_message(ENOENT, "Team not found"), 404

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, "User not found"), 404

        if team.owner != user:
            if team.organization.owner != user:
                return response_message(EINVAL, 'You are not the team owner'), 403

        team.organization.modify(pull__teams=team)

        try:
            shutil.rmtree(USERS_ROOT / team.organization.path / team.path)
        except FileNotFoundError:
            pass

        User.objects.update(pull__teams=team)

        tests = Test.objects(team=team)
        for test in tests:
            tasks = Task.objects(test=test)
            for task in tasks:
                TestResult.objects(task=task).delete()
            tasks.delete()
        tests.delete()
        TaskQueue.objects(team=team).update(to_delete=True, organization=None, team=None)
        team.delete()

@api.route('/avatar/<team_id>')
class TeamAvatar(Resource):
    @api.doc('get the avatar of a team')
    def get(self, team_id):
        """Get the avatar of a team"""
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    team = Team.objects(pk=team_id).first()
                    if team:
                        return send_from_directory(Path(os.getcwd()) / USERS_ROOT / team.organization.path / team.path, team.avatar)
                    return response_message(USER_NOT_EXIST, 'Team not found'), 404
                return response_message(USER_NOT_EXIST), 404
            return response_message(TOKEN_ILLEGAL, payload), 401
        return response_message(TOKEN_REQUIRED), 400

@api.route('/member')
class TeamMember(Resource):
    @token_required
    @api.doc('quit the team')
    @api.expect(_team_id)
    def delete(self, **kwargs):
        """
        Quit the team
        
        The user logged in will quit the team
        """
        user_id = kwargs['user']['user_id']
        team_id = request.json.get('team_id', None)
        if not team_id:
            return response_message(EINVAL, "Field team_id is required"), 400

        team_to_quit = Team.objects(pk=team_id).first()
        if not team_to_quit:
            return response_message(ENOENT, "Team not found"), 404

        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, "User not found"), 404

        for team in user.teams:
            if team != team_to_quit:
                continue
            if team.owner == user:
                return response_message(EPERM, "Can't quit the team as you are the owner"), 403
            team.modify(pull__members=user)
            user.modify(pull__teams=team)
            return response_message(SUCCESS), 200
        else:
            return response_message(EINVAL, "User is not in the team"), 400

@api.route('/all')
class TeamListAll(Resource):
    @token_required
    @api.doc('list all teams of an organization')
    @api.param('organization_id', description='The organization ID')
    @api.marshal_list_with(_team)
    def get(self, **kwargs):
        """List all teams of an organization"""
        ret = []

        organization_id = request.args.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, 'Field organization_id is required'), 400

        teams = Team.objects(organization=ObjectId(organization_id))
        return [{
                'label': team.name,
                'owner': team.owner.name,
                'owner_email': team.owner.email,
                'organization_id': organization_id,
                'value': str(team.id)
            } for team in teams]

@api.route('/join')
class TeamJoin(Resource):
    @token_required
    @api.doc('Join a team')
    @api.expect(_team_id)
    def post(self, user):
        """The logged in user joins a team"""
        team_id = request.json.get('team_id', None)
        if not team_id:
            return response_message(EINVAL, "Field id is required"), 400

        user = User.objects(pk=user['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        team = Team.objects(pk=team_id).first()
        if not team:
            return response_message(ENOENT, 'Team not found'), 404

        if user not in team.members:
            team.modify(push__members=user)
        if team not in user.teams:
            user.modify(push__teams=team)

@api.route('/users')
class OrganizationUsers(Resource):
    @token_required
    @api.doc('list all users')
    @api.param('team_id', description='The team ID')
    @api.marshal_list_with(_user)
    def get(self, **kwargs):
        """
        List all users of a team
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        team_id = request.args.get('team_id', None)
        if not team_id:
            return response_message(EINVAL, 'Field team_id is required'), 401

        team = Team.objects(pk=team_id).first()
        if not team:
            return response_message(ENOENT, 'Team not found'), 404

        if user not in team.members:
            if user not in team.organization.members:
                return response_message(EPERM, 'You are not in the organization'), 403

        return [{'value': str(m.id), 'label': m.name, 'email': m.email} for m in team.members]
