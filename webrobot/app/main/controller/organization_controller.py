import os
import shutil
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource
from bson import ObjectId

from app.main.util.decorator import token_required
from app.main.model.database import *
from task_runner.runner import start_threads

from ..service.auth_helper import Auth
from ..util.dto import OrganizationDto
from ..util.errors import *
from ..config import get_config
from ..util.identicon import *

USERS_ROOT = Path(get_config().USERS_ROOT)

api = OrganizationDto.api
_organization = OrganizationDto.organization


@api.route('/')
class OrganizationList(Resource):
    @token_required
    @api.doc('List all organizations associated with the user')
    def get(self, **kwargs):
        ret = []
        check = []
        user_id = kwargs['user']['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        organizations = Organization.objects(owner=ObjectId(user_id), name__not__exact='Personal')
        for organization in organizations:
            ret.append({
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'value': str(organization.id)
            })
            check.append(organization)

        for organization in user.organizations:
            if organization in check or organization.name == 'Personal':
                continue
            ret.append({
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'value': str(organization.id)
            })

        return ret

    @token_required
    @api.doc('Create a new organization')
    def post(self, **kwargs):
        data = request.json
        name = data.get('name', None)
        if not name:
            return error_message(EINVAL, 'Field name is required'), 400
        
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        org = Organization(name=name)
        org.owner = user
        org.members.append(user)
        org.save()
        user.organizations.append(org)
        user.save()

        org.path = name + '#' + str(org.id)
        org_root = USERS_ROOT / org.path
        try:
            os.mkdir(org_root)
        except FileExistsError as e:
            return error_message(EEXIST), 401

        img= render_identicon(hash(name), 27)
        img.save(org_root / ('%s.png' % org.id))
        org.avatar = '%s.png' % org.id
        org.save()

    @token_required
    @api.doc('Delete a organization')
    def delete(self, **kwargs):
        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return error_message(EINVAL, "Field organization_id is required"), 400

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return error_message(ENOENT, "Team not found"), 404

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return error_message(ENOENT, "User not found"), 404

        if organization.owner != user:
            return error_message(EINVAL, 'You are not the organization owner'), 403

        EventQueue.objects(organization=organization).update(to_delete=True, organization=None, team=None)

        try:
            shutil.rmtree(USERS_ROOT / organization.path)
        except FileNotFoundError:
            pass

        User.objects.update(pull__organizations=organization)

        # Tests belong to teams of the organization will be deleted as well by this query
        tests = Test.objects(organization=organization)
        for test in tests:
            tasks = Task.objects(test=test)
            for task in tasks:
                TestResult.objects(task=task).delete()
            tasks.delete()
        tests.delete()
        TaskQueue.objects(organization=organization).update(to_delete=True, organization=None, team=None)
        
        teams = Team.objects(organization=organization)
        for team in teams:
            User.objects.update(pull__teams=team)
            team.delete()

        organization.delete()

@api.route('/avatar/<org_id>')
class OrganizationAvatar(Resource):
    @api.doc('get the avatar for an organization')
    def get(self, org_id):
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    org = Organization.objects(pk=org_id).first()
                    if org:
                        return send_from_directory(Path(os.getcwd()) / USERS_ROOT / org.path, org.avatar)
                    return error_message(USER_NOT_EXIST, 'Organization not found'), 404
                return error_message(USER_NOT_EXIST), 404
            return error_message(TOKEN_ILLEGAL, payload), 401
        return error_message(TOKEN_REQUIRED), 400

@api.route('/member')
class OrganizationMember(Resource):
    @token_required
    @api.doc('Quit the organization')
    def delete(self, **kwargs):
        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return error_message(EINVAL, "Field organization_id is required"), 400

        org_to_quit = Organization.objects(pk=organization_id).first()
        if not org_to_quit:
            return error_message(ENOENT, "Organization not found"), 404

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return error_message(ENOENT, "User not found"), 404

        for organization in user.organizations:
            if organization != org_to_quit:
                continue
            if organization.owner == user:
                return error_message(EPERM, "Can't quit the organization as you are the owner"), 403
            organization.modify(pull__members=user)
            user.modify(pull__organizations=organization)
            return error_message(SUCCESS), 200
        else:
            return error_message(EINVAL, "User is not in the organization"), 400

@api.route('/all')
class OrganizationListAll(Resource):
    @token_required
    @api.doc('List all organizations registered')
    def get(self, **kwargs):
        ret = []

        organizations = Organization.objects(name__not__exact='Personal')
        for organization in organizations:
            r = {
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'value': str(organization.id)
            }
            ret.append(r)
        return ret

@api.route('/include_team')
class OrganizationListAll(Resource):
    @token_required
    @api.doc('List all organizations registered')
    def get(self, **kwargs):
        ret = []
        check = []
        user_id = kwargs['user']['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        organizations = Organization.objects(owner=ObjectId(user_id))
        for organization in organizations:
            r = {
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'value': str(organization.id)
            }
            ret.append(r)
            check.append(organization)
            if not 'teams' in organization:
                continue
            if len(organization.teams) > 0:
                r['children'] = []
            for team in organization.teams:
                r['children'].append({
                    'label': team.name,
                    'owner': team.owner.name,
                    'owner_email': team.owner.email,
                    'value': str(team.id)
                })

        for organization in user.organizations:
            if organization in check:
                continue
            r = {
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'value': str(organization.id)
            }
            ret.append(r)
            if not 'teams' in organization:
                continue
            if len(organization.teams) > 0:
                r['children'] = []
            for team in organization.teams:
                r['children'].append({
                    'label': team.name,
                    'owner': team.owner.name,
                    'owner_email': team.owner.email,
                    'value': str(team.id)
                })

        return ret

@api.route('/join')
class OrganizationJoin(Resource):
    @token_required
    @api.doc('join an organization')
    def post(self, **kwargs):
        org_id = request.json.get('id', None)
        if not org_id:
            return error_message(EINVAL, "Field id is required"), 400

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        organization = Organization.objects(pk=org_id).first()
        if not organization:
            return error_message(ENOENT, 'Organization not found'), 404

        if user not in organization.members:
            organization.modify(push__members=user)
        if organization not in user.organizations:
            user.modify(push__organizations=organization)

        start_threads(user)

@api.route('/users')
class OrganizationUsers(Resource):
    @token_required
    @api.doc('List all users of the specified organization')
    def get(self, **kwargs):
        organization_id = request.args.get('organization', None)
        if organization_id:
            organization = Organization.objects(pk=organization_id).first()
            if not organization:
                return error_message(ENOENT, 'Organization not found'), 404
            return [{'value': str(m.id), 'label': m.name, 'email': m.email} for m in organization.members]

        team_id = request.args.get('team', None)
        if team_id:
            team = Team.objects(pk=team_id).first()
            if not team:
                return error_message(ENOENT, 'Team not found'), 404
            return [{'value': str(m.id), 'label': m.name, 'email': m.email} for m in team.members]

@api.route('/transfer')
class OrganizationTransfer(Resource):
    @token_required
    @api.doc('Transfer ownership of an organization to another authorized user')
    def post(self, **kwargs):
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return error_message(ENOENT, 'User not found'), 404

        organization_id = request.json.get('organization', None)
        if not organization_id:
            return error_message(EINVAL, 'Field organization is required'), 401

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return error_message(ENOENT, 'Organization not found'), 404

        if organization.owner != user:
            return error_message(EPERM, 'You are not the organization owner'), 403

        owner_id = request.json.get('new_owner', None)
        if not owner_id:
            return error_message(EINVAL, 'Field new_owner is required'), 401

        owner = User.objects(pk=owner_id).first()
        if not owner:
            return error_message(ENOENT, 'New owner not found'), 404

        organization.owner = owner
        organization.save()
