from functools import wraps

from flask import request
from mongoengine import ValidationError

from app.main.service.auth_helper import Auth
from ..util.response import *
from ..model.database import *
from ..util import js2python_bool, js2python_variable


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        ret, status = Auth.get_logged_in_user(request.headers.get('X-Token'))
        if status != 200:
            return ret, status
        kwargs['user'] = ret['data']

        return f(*args, **kwargs)

    return decorated

def token_required_if_proprietary(args, kwargs):
    data = kwargs['data']
    user = None
    organization = None
    team = None
    proprietary = js2python_bool(data.get('proprietary', False))

    if proprietary:
        ret, status = Auth.get_logged_in_user(request.headers.get('X-Token'))
        if status != 200:
            return ret, status
        kwargs['user'] = ret['data']
        user = User.objects(pk=kwargs['user']['user_id']).first()
        organization = None
        team = None

        org_id = data.get('organization', None)
        team_id = data.get('team', None)
        if js2python_variable(team_id):
            team = Team.objects(pk=team_id).first()
            if not team:
                return response_message(ENOENT, 'Team not found'), 404
            if team not in user.teams:
                return response_message(EINVAL, 'Your are not a team member'), 400
        if js2python_variable(org_id):
            organization = Organization.objects(pk=org_id).first()
            if not organization:
                return response_message(ENOENT, 'Organization not found'), 404
            if organization not in user.organizations:
                return response_message(EINVAL, 'You are not an organization member'), 400
        kwargs['team'] = team
        kwargs['organization'] = organization
    kwargs['proprietary'] = proprietary

    return None, 200

def token_required_if_proprietary_by_args(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.args
        ret, status = token_required_if_proprietary(args, kwargs)
        if status != 200:
            return ret, status

        return f(*args, **kwargs)

    return decorated

def token_required_if_proprietary_by_json(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.json
        ret, status = token_required_if_proprietary(args, kwargs)
        if status != 200:
            return ret, status

        return f(*args, **kwargs)

    return decorated

def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        ret, status = Auth.get_logged_in_user(request.headers.get('X-Token'))
        if status != 200:
            return ret, status

        data = ret.get('data')
        roles = data.get('roles')
        if 'admin' not in roles:
            return response_message(ADMIN_TOKEN_REQUIRED), 401

        return f(*args, **kwargs)

    return decorated

def organization_team_required(*args, **kwargs):
    data = kwargs['data']
    user = kwargs['user']
    organization = None
    team = None

    user = User.objects(pk=user['user_id']).first()
    if not user:
        return response_message(ENOENT, 'User not found'), 404

    org_id = data.get('organization', None)
    team_id = data.get('team', None)
    if js2python_variable(team_id):
        team = Team.objects(pk=team_id).first()
        if not team:
            return response_message(ENOENT, 'Team not found'), 404
        if team not in user.teams:
            return response_message(EINVAL, 'Field organization_team is incorrect, not a team member joined'), 400
    if js2python_variable(org_id):
        organization = Organization.objects(pk=org_id).first()
        if not organization:
            return response_message(ENOENT, 'Organization not found'), 404
        if organization not in user.organizations:
            return response_message(EINVAL, 'Field organization_team is incorrect, not a organization member joined'), 400

    if not organization:
        return response_message(EINVAL, 'Please select an organization or team first'), 400

    return (user, team, organization), 200

def organization_team_required_by_args(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.args
        ret, status = organization_team_required(*args, **kwargs)
        if status != 200:
            return ret, status

        user, team, organization = ret
        kwargs['user'] = user
        kwargs['team'] = team
        kwargs['organization'] = organization

        return f(*args, **kwargs)

    return decorated

def organization_team_required_by_json(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.json
        ret, status = organization_team_required(*args, **kwargs)
        if status != 200:
            return ret, status

        user, team, organization = ret
        kwargs['user'] = user
        kwargs['team'] = team
        kwargs['organization'] = organization

        return f(*args, **kwargs)

    return decorated

def organization_team_required_by_form(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.form
        ret, status = organization_team_required(*args, **kwargs)
        if status != 200:
            return ret, status

        user, team, organization = ret
        kwargs['user'] = user
        kwargs['team'] = team
        kwargs['organization'] = organization

        return f(*args, **kwargs)

    return decorated

def task_required(f):
    '''
    Should only be used after organization_team_required_by_xxx family decorators to reuse field data in the kwargs
    '''
    @wraps(f)
    def decorated(*args, **kwargs):
        data = kwargs['data']
        organization = kwargs['organization']
        team = kwargs['team']

        task_id = data.get('task_id', None)
        if not task_id:
            return response_message(EINVAL, 'Field task_id is required'), 400

        try:
            task = Task.objects(pk=task_id).get()
        except ValidationError as e:
            return response_message(EINVAL, 'Task ID incorrect'), 400
        except Task.DoesNotExist:
            return response_message(ENOENT, 'Task not found'), 404
        
        if task.organization != organization or task.team != team:
            return response_message(EPERM, 'Accessing resources that not belong to you is not allowed'), 403

        kwargs['task'] = task

        return f(*args, **kwargs)

    return decorated
