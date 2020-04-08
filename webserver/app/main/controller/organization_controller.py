import os
import shutil
from pathlib import Path
from flask import request, send_from_directory
from flask_restx import Resource
from bson import ObjectId

from app.main.util.decorator import token_required
from app.main.model.database import *

from ..service.auth_helper import Auth
from ..util.dto import OrganizationDto
from ..util.response import *
from ..config import get_config
from ..util.identicon import *

USERS_ROOT = Path(get_config().USERS_ROOT)

api = OrganizationDto.api
_user = OrganizationDto.user
_organization = OrganizationDto.organization
_new_organization = OrganizationDto.new_organization
_organization_id = OrganizationDto.organization_id
_organization_team_resp = OrganizationDto.organization_team_resp
_transfer_ownership = OrganizationDto.transfer_ownership


@api.route('/')
class OrganizationList(Resource):
    @token_required
    @api.doc('list all organizations')
    @api.marshal_list_with(_organization)
    def get(self, **kwargs):
        """List all organizations joined by the logged in user"""
        ret = []
        check = []
        user_id = kwargs['user']['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organizations = Organization.objects(owner=user)
        for organization in organizations:
            ret.append({
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'personal': organization.personal,
                'value': str(organization.id)
            })
            check.append(organization)

        for organization in user.organizations:
            if organization in check:
                continue
            ret.append({
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'personal': organization.personal,
                'value': str(organization.id)
            })

        ret.sort(key=lambda x: not x['personal'])
        return ret

    @token_required
    @api.doc('create a new organization')
    @api.expect(_new_organization)
    def post(self, **kwargs):
        """
        Create a new organization

        Note: The logged in user performing the operation will become the owner of the organization
        """
        data = request.json
        name = data.get('name', None)
        if not name:
            return response_message(EINVAL, 'Field name is required'), 400
        
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

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
            return response_message(EEXIST), 401

        img= render_identicon(hash(name), 27)
        img.save(org_root / ('%s.png' % org.id))
        org.avatar = '%s.png' % org.id
        org.save()

    @token_required
    @api.doc('delete an organization')
    @api.expect(_organization_id)
    def delete(self, **kwargs):
        """
        Delete an organization

        Note: Only the owner of the organization could perform this operation
        """
        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, "Field organization_id is required"), 400

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return response_message(ENOENT, "Team not found"), 404

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, "User not found"), 404

        if organization.owner != user:
            return response_message(EINVAL, 'You are not the organization owner'), 403

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
    @api.doc('get the avatar of an organization')
    def get(self, org_id):
        """Get the avatar of an organization"""
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    org = Organization.objects(pk=org_id).first()
                    if org:
                        if org.avatar:
                            return send_from_directory(Path(os.getcwd()) / USERS_ROOT / org.path, org.avatar)
                        else:
                            return send_from_directory(Path(os.getcwd()) / USERS_ROOT / org.path, org.owner.avatar)
                    return response_message(USER_NOT_EXIST, 'Organization not found'), 404
                return response_message(USER_NOT_EXIST), 404
            return response_message(TOKEN_ILLEGAL, payload), 401
        return response_message(TOKEN_REQUIRED), 400

@api.route('/member')
class OrganizationMember(Resource):
    @token_required
    @api.doc('quit the organization')
    @api.expect(_organization_id)
    def delete(self, **kwargs):
        """
        Quit the organization
        
        The user logged in will quit the organization
        """
        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, "Field organization_id is required"), 400

        org_to_quit = Organization.objects(pk=organization_id).first()
        if not org_to_quit:
            return response_message(ENOENT, "Organization not found"), 404

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, "User not found"), 404

        for organization in user.organizations:
            if organization != org_to_quit:
                continue
            if organization.owner == user:
                return response_message(EPERM, "Can't quit the organization as you are the owner"), 403
            organization.modify(pull__members=user)
            user.modify(pull__organizations=organization)
            return response_message(SUCCESS), 200
        else:
            return response_message(EINVAL, "User is not in the organization"), 400

@api.route('/all')
class OrganizationListAll(Resource):
    @token_required
    @api.doc('list all organizations registered')
    @api.marshal_list_with(_organization)
    def get(self, **kwargs):
        """List all organizations registered"""
        ret = []

        organizations = Organization.objects(name__not__exact='Personal')
        return [{
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'personal': organization.personal,
                'value': str(organization.id)
            } for organization in organizations]

@api.route('/include_team')
class OrganizationListAll(Resource):
    @token_required
    @api.doc('list all organizations and teams registered')
    @api.marshal_list_with(_organization_team_resp)
    def get(self, **kwargs):
        """List all organizations and teams registered"""
        ret = []
        check = []
        user_id = kwargs['user']['user_id']
        user = User.objects(pk=user_id).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organizations = Organization.objects(owner=user)
        for organization in organizations:
            r = {
                'label': organization.name,
                'owner': organization.owner.name,
                'owner_email': organization.owner.email,
                'personal': organization.personal,
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
                'personal': organization.personal,
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
    @api.expect(_organization_id)
    def post(self, **kwargs):
        """The logged in user joins an organization"""
        org_id = request.json.get('organization_id', None)
        if not org_id:
            return response_message(EINVAL, "Field organization_id is required"), 400

        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organization = Organization.objects(pk=org_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404

        if user not in organization.members:
            organization.modify(push__members=user)
        if organization not in user.organizations:
            user.modify(push__organizations=organization)

@api.route('/users')
class OrganizationUsers(Resource):
    @token_required
    @api.doc('list all users')
    @api.param('organization_id', description='The organization ID')
    @api.marshal_list_with(_user)
    def get(self, **kwargs):
        """
        List all users of an organization

        Note: Users in a team of the organization will not be counted.
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organization_id = request.args.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, 'Field organization_id is required'), 401

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404

        if user not in organization.members:
            return response_message(EPERM, 'You are not in the organization'), 403

        return [{'value': str(m.id), 'label': m.name, 'email': m.email} for m in organization.members]

@api.route('/all_users')
class OrganizationUsers(Resource):
    @token_required
    @api.doc('list all users')
    @api.param('organization_id', description='The organization ID')
    @api.marshal_list_with(_user)
    def get(self, **kwargs):
        """
        List all users of an organization

        Note: Users in a team of the organization will be counted.
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organization_id = request.args.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, 'Field organization_id is required'), 401

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404

        if user not in organization.members:
            return response_message(EPERM, 'You are not in the organization'), 403

        ret = [{'value': str(m.id), 'label': m.name, 'email': m.email} for m in organization.members]
        check_list = [str(m.id) for m in organization.members]

        for team in organization.teams:
            for user in team.members:
                user_id = str(user.id)
                if user_id not in check_list:
                    ret.append({'value': user_id, 'label': user.name, 'email': user.email})
                    check_list.append(user_id)

        return ret

@api.route('/transfer')
class OrganizationTransfer(Resource):
    @token_required
    @api.doc('transfer ownership of an organization')
    @api.expect(_transfer_ownership)
    def post(self, **kwargs):
        """
        Transfer the ownership of an organization to another authorized user.

        Note: The new owner should have joined the organization or a team of the organization
        """
        user = User.objects(pk=kwargs['user']['user_id']).first()
        if not user:
            return response_message(ENOENT, 'User not found'), 404

        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return response_message(EINVAL, 'Field organization_id is required'), 401

        organization = Organization.objects(pk=organization_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404

        if organization.owner != user:
            return response_message(EPERM, 'You are not the organization owner'), 403

        owner_id = request.json.get('new_owner', None)
        if not owner_id:
            return response_message(EINVAL, 'Field new_owner is required'), 401

        owner = User.objects(pk=owner_id).first()
        if not owner:
            return response_message(ENOENT, 'New owner not found'), 404

        if owner not in organization.members:
            for team in organization.teams:
                if owner in team.members:
                    break
            else:
                return response_message(EPERM, 'New owner should be a member of the organization'), 403

        organization.owner = owner
        if owner not in organization.members:
            organization.members.append(owner)
        organization.save()

        for team in organization.teams:
            if team.owner == user:
                team.owner = owner
                if owner not in team.members:
                    team.members.append(owner)
                team.save()
