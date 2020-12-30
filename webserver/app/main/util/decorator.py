from bson import ObjectId
from functools import wraps

from app.main.service.auth_helper import Auth
from sanic.response import json
from sanic.views import HTTPMethodView

from ..model.database import Organization, Task, Team, User
from ..util import js2python_bool, js2python_variable
from ..util.response import SUCCESS, EINVAL, ENOENT, EPERM, response_message, USER_NOT_EXIST, ADMIN_TOKEN_REQUIRED


def token_required(f):
    @wraps(f)
    async def decorator(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        ret = await Auth.get_logged_in_user(request.headers.get('X-Token'))
        if ret['code'] != SUCCESS[0]:
            return json(ret)

        request.ctx.user = await User.find_one({'_id': ObjectId(ret['data']['user_id'])})

        return await f(*args, **kwargs)
    return decorator

async def token_required_if_proprietary(request, args, kwargs):
    data = request.ctx.data
    proprietary = js2python_bool(data.get('proprietary', False))

    if proprietary:
        ret = await Auth.get_logged_in_user(request.headers.get('X-Token'))
        if ret['code'] != SUCCESS[0]:
            return json(ret)
        user = await User.find_one({'_id': ObjectId(ret['data']['user_id'])})
        request.ctx.user = user
        organization = None
        team = None

        org_id = data.get('organization', None)
        team_id = data.get('team', None)
        if team_id and team_id != 'undefined' and team_id != 'null':
            team = await Team.find_one({'_id': ObjectId(team_id)})
            if not team:
                return response_message(ENOENT, 'Team not found')
            if team not in user.teams:
                return response_message(EINVAL, 'Your are not a team member')
        if org_id and org_id != 'undefined' and org_id != 'null':
            organization = await Organization.find_one({'_id': ObjectId(org_id)})
            if not organization:
                return response_message(ENOENT, 'Organization not found')
            if organization not in user.organizations:
                return response_message(EINVAL, 'You are not an organization member')

        request.ctx.team = team
        request.ctx.organization = organization

    return response_message(SUCCESS)

def token_required_if_proprietary_by_args(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        request.ctx.data = request.args
        ret = await token_required_if_proprietary(request, args, kwargs)
        if ret['code'] != SUCCESS[0]:
            return json(ret)

        return await f(*args, **kwargs)

    return decorated

def token_required_if_proprietary_by_json(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        request.ctx.data = request.json
        ret = await token_required_if_proprietary(request, args, kwargs)
        if ret['code'] != SUCCESS[0]:
            return json(ret)

        return await f(*args, **kwargs)

    return decorated

def admin_token_required(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        ret = await Auth.get_logged_in_user(request.headers.get('X-Token'))
        if ret['code'] != SUCCESS[0]:
            return json(ret)

        user = await User.find_one({'_id': ObjectId(ret['data']['user_id'])})
        request.ctx.user = user

        if not user.is_admin():
            return json(response_message(ADMIN_TOKEN_REQUIRED))

        return await f(*args, **kwargs)
    return decorated

async def organization_team_required(request, *args, **kwargs):
    data = request.ctx.data
    user = request.ctx.user
    organization = None
    team = None

    org_id = data.get('organization', None)
    team_id = data.get('team', None)
    if js2python_variable(team_id):
        team = await Team.find_one({'_id': ObjectId(team_id)})
        if not team:
            return response_message(ENOENT, 'Team not found')
        if team not in user.teams:
            return response_message(EINVAL, 'Field organization_team is incorrect, not a team member joined')
    if js2python_variable(org_id):
        organization = await Organization.find_one({'_id': ObjectId(org_id)})
        if not organization:
            return response_message(ENOENT, 'Organization not found')
        if organization not in user.organizations:
            return response_message(EINVAL, 'Field organization_team is incorrect, not a organization member joined')

    if not organization:
        return response_message(EINVAL, 'Please select an organization or team first')

    request.ctx.team = team
    request.ctx.organization = organization

    return response_message(SUCCESS)

def organization_team_required_by_args(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        request.ctx.data = request.args
        ret = await organization_team_required(request, *args, **kwargs)
        if ret['code'] != SUCCESS[0]:
            return json(ret)
        return await f(*args, **kwargs)
    return decorated

def organization_team_required_by_json(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        request.ctx.data = request.json
        ret = await organization_team_required(request, *args, **kwargs)
        if ret['code'] != SUCCESS[0]:
            return json(ret)
        return await f(*args, **kwargs)
    return decorated

def organization_team_required_by_form(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        request.ctx.data = request.form
        ret = await organization_team_required(request, *args, **kwargs)
        if ret['code'] != SUCCESS[0]:
            return json(ret)
        return await f(*args, **kwargs)
    return decorated

def task_required(f):
    '''
    Should only be used after organization_team_required_by_xxx family decorators to reuse field data in the kwargs
    '''
    @wraps(f)
    async def decorated(*args, **kwargs):
        request = args[0]
        if isinstance(args[0], HTTPMethodView):
            request = args[1]

        data = request.ctx.data
        organization = request.ctx.organization
        team = request.ctx.team

        task_id = data.get('task_id', None)
        if not task_id:
            return json(response_message(EINVAL, 'Field task_id is required'))

        task = await Task.find_one({'_id': ObjectId(task_id)})
        if not task:
            return json(response_message(ENOENT, 'Task not found'))
        
        if task.organization != organization or task.team != team:
            return json(response_message(EPERM, 'Accessing resources that not belong to you is not allowed'))

        request.ctx.task = task

        return await f(*args, **kwargs)

    return decorated
