from functools import wraps

from flask import request

from app.main.service.auth_helper import Auth
from ..util.errors import *
from ..model.database import *


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS[0]:
            return data, status
        kwargs['user'] = data['data']

        return f(*args, **kwargs)

    return decorated


def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        data, status = Auth.get_logged_in_user(request)
        token = data.get('data')

        if data.get('code') != SUCCESS[0]:
            return data, status

        roles = token.get('roles')
        if 'admin' not in roles:
            return error_message(ADMIN_TOKEN_REQUIRED), 401

        return f(*args, **kwargs)

    return decorated

def organization_team_required(*args, **kwargs):
    data = kwargs['data']
    user = kwargs['user']
    organization = None
    team = None

    user = User.objects(pk=user['user_id']).first()
    if not user:
        return error_message(ENOENT, 'User not found'), 404

    org_id = data.get('organization', None)
    team_id = data.get('team', None)
    if team_id and team_id != 'undefined':
        team = Team.objects(pk=team_id).first()
        if not team:
            return error_message(ENOENT, 'Team not found'), 404
        if team not in user.teams:
            return error_message(EINVAL, 'Field organization_team is incorrect, not a team member joined'), 400
    if org_id and org_id != 'undefined':
        organization = Organization.objects(pk=org_id).first()
        if not organization:
            return error_message(ENOENT, 'Organization not found'), 404
        if organization not in user.organizations:
            return error_message(EINVAL, 'Field organization_team is incorrect, not a organization member joined'), 400

    if not organization:
        return error_message(EINVAL, 'Please select an organization or team first'), 400

    return user, team, organization

def organization_team_required_by_args(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        kwargs['data'] = request.args
        ret = organization_team_required(*args, **kwargs)
        if len(ret) != 3:
            return ret

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
        ret = organization_team_required(*args, **kwargs)
        if len(ret) != 3:
            return ret

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
        ret = organization_team_required(*args, **kwargs)
        if len(ret) != 3:
            return ret

        user, team, organization = ret
        kwargs['user'] = user
        kwargs['team'] = team
        kwargs['organization'] = organization

        return f(*args, **kwargs)

    return decorated

def task_required(f):
    '''
    Should used after organization_team_required_by_xxx series decorators to reuse field data in the kwargs
    '''
    @wraps(f)
    def decorated(*args, **kwargs):
        data = kwargs['data']
        organization = kwargs['organization']
        team = kwargs['team']

        task_id = data.get('task_id', None)
        if not task_id:
            return error_message(EINVAL, 'Field task_id is required'), 400

        try:
            task = Task.objects(pk=task_id).get()
        except ValidationError as e:
            print(e)
            return error_message(EINVAL, 'Task ID incorrect'), 400
        except Task.DoesNotExist:
            return error_message(ENOENT, 'Task not found'), 404
        
        if task.organization != organization or task.team != team:
            return error_message(EPERM, 'Accessing resources that not belong to you is not allowed'), 403

        kwargs['task'] = task

        return f(*args, **kwargs)

    return decorated
