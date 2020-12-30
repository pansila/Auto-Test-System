import asyncio
import aiofiles
import base64
import os
from pathlib import Path
from bson import ObjectId
from async_files.utils import async_wraps

from sanic.log import logger
from sanic_openapi import doc
from sanic.response import json, file
from sanic import Blueprint
from sanic.views import HTTPMethodView

from ..util import async_rmtree
from ..util.decorator import token_required
from ..model.database import User, Organization, Team, Test, TestResult, TaskQueue, Task

from ..service.auth_helper import Auth
from ..util.dto import TeamDto, json_response
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, EEXIST, EPERM, USER_NOT_EXIST, TOKEN_REQUIRED, TOKEN_ILLEGAL
from ..config import get_config
from ..util.identicon import render_identicon

USERS_ROOT = Path(get_config().USERS_ROOT)

_user = TeamDto.user
_user_list = TeamDto.user_list
_team_list = TeamDto.team_list
_new_team = TeamDto.new_team
_team_id = TeamDto.team_id
_team_avatar = TeamDto.team_avatar


bp = Blueprint('team', url_prefix='/team')

class TeamView(HTTPMethodView):
    @doc.summary('List all teams joined by the logged in user')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.produces(_team_list)
    @token_required
    async def get(self, request):
        ret = []
        check = []
        user = request.ctx.user

        async for team in Team.find({'owner': user.pk}):
            owner = await team.owner.fetch()
            organization = await team.organization.fetch()
            ret.append({
                'label': team.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'organization_id': str(organization.pk),
                'value': str(team.id)
            })
            check.append(team)

        for team in user.teams:
            if team in check:
                continue
            organization = await team.organization.fetch()
            owner = await team.owner.fetch()
            ret.append({
                'label': team.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'organization_id': str(organization.pk),
                'value': str(team.id)
            })

        return json(response_message(SUCCESS, teams=ret))

    @doc.summary('create a new team')
    @doc.description('The logged in user performing the operation will become the owner of the team')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_new_team, location='body')
    @doc.produces(json_response)
    @token_required
    async def post(self, request):
        data = request.json
        user = request.ctx.user

        name = data.get('name', None)
        if not name:
            return json(response_message(EINVAL, 'Field name is required'))

        organization_id = data.get('organization_id', None)
        if not organization_id:
            return json(response_message(EINVAL, 'Field organization_id is required'))
        
        organization = await Organization.find_one({'_id': ObjectId(organization_id)})
        if not organization:
            return json(response_message(ENOENT, 'Organization not found'))

        if organization.owner != user:
            return json(response_message(EINVAL, 'Your are not the organization\'s owner'))

        team = await Team.find_one({'name': name, 'organization': organization.pk})
        if team:
            return json(response_message(EEXIST, 'Team has been registered'))

        team = Team(name=name, organization=organization.pk, owner=user.pk)
        team.members.append(user)
        await team.commit()
        user.teams.append(team)
        await user.commit()
        organization.teams.append(team)
        await organization.commit()

        team.path = name + '#' + str(team.id)
        team_root = USERS_ROOT / organization.path / team.path
        try:
            await aiofiles.os.mkdir(team_root)
        except FileExistsError as e:
            return json(response_message(EEXIST))

        img = await render_identicon(hash(name), 27)
        await async_wraps(img.save)(team_root / ('%s.png' % team.id))
        team.avatar = '%s.png' % team.id
        await team.commit()

        return json(response_message(SUCCESS))

    @doc.summary('delete a team')
    @doc.description('Only the owner of the team or the organization that the team belongs to could perform this operation')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_team_id, location='body')
    @doc.produces(json_response)
    @token_required
    async def delete(self, request):
        team_id = request.json.get('team_id', None)
        if not team_id:
            return json(response_message(EINVAL, "Field team_id is required"))

        team = await Team.find_one({'_id': ObjectId(team_id)})
        if not team:
            return json(response_message(ENOENT, "Team not found"))

        user = request.ctx.user
        organization = await team.organization.fetch()
        if await team.owner.fetch() != user:
            if await organization.owner.fetch() != user:
                return json(response_message(EINVAL, 'You are not the team owner'))

        organization.teams.remove(team)
        await organization.commit()

        try:
            await async_rmtree(USERS_ROOT / organization.path / team.path)
        except FileNotFoundError:
            pass

        user.teams.remove(team)
        await user.commit()

        async for test in Test.find({'team': team.pk}):
            async for task in Task.find({'test': test.pk}):
                async for ts in TestResult.find({'task': task.pk}):
                    await ts.delete()
                await task.delete()
            await test.delete()
        async for queue in TaskQueue.find({'team': team.pk}):
            queue.to_delete = True
            queue.organization = None
            queue.team = None
            await queue.commit()
        await team.delete()

        return json(response_message(SUCCESS))

@bp.get('/avatar/<team_id>')
@doc.summary('get the avatar of a team')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(_team_avatar)
@token_required
async def handler(request, team_id):
    user = request.ctx.user
    team = await Team.find_one({'_id': ObjectId(team_id)})
    if team:
        organization = await team.organization.fetch()
        async with aiofiles.open(USERS_ROOT / organization.path / team.path / team.avatar, 'rb') as img:
            _, ext = os.path.splitext(team.avatar)
            return json(response_message(SUCCESS, type=f'image/{ext[1:]}', data=base64.b64encode(await img.read()).decode('ascii')))
    return json(response_message(USER_NOT_EXIST, 'Team not found'))

@bp.delete('/member')
@doc.summary('let current logged in user quit the team')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_team_id, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    team_id = request.json.get('team_id', None)
    if not team_id:
        return json(response_message(EINVAL, "Field team_id is required"))

    team_to_quit = await Team.find_one({'_id': ObjectId(team_id)})
    if not team_to_quit:
        return json(response_message(ENOENT, "Team not found"))

    user = request.ctx.user

    for team in user.teams:
        if team != team_to_quit:
            continue
        if await team.owner.fetch() == user:
            return json(response_message(EPERM, "Can't quit the team as you are the owner"))
        team.members.remove(user)
        await team.commit()
        user.teams.remove(team)
        await user.commit()
        return json(response_message(SUCCESS))
    else:
        return json(response_message(EINVAL, "User is not in the team"))

@bp.get('/all')
@doc.summary('list all teams of an organization')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(doc.String(name='organization_id', description='The organization ID'))
@doc.produces(_team_list)
@token_required
async def handler(request):
    ret = []

    organization_id = request.args.get('organization_id', None)
    if not organization_id:
        return json(response_message(EINVAL, 'Field organization_id is required'))

    user = request.ctx.user
    organization = await Organization.find_one({'_id': ObjectId(organization_id)})
    if not organization:
        return json(response_message(ENOENT, 'Organization not found'))
    if user not in organization.members:
        return json(response_message(EPERM, 'You are not a member of the organization'))

    async for team in Team.find({'organization': ObjectId(organization_id)}):
        owner = await team.owner.fetch()
        ret.append({
            'label': team.name,
            'owner': owner.name,
            'owner_email': owner.email,
            'organization_id': organization_id,
            'value': str(team.pk)
        })
    return json(response_message(SUCCESS, teams=ret))

@bp.post('/join')
@doc.summary('join a team')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_team_id, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    team_id = request.json.get('team_id', None)
    if not team_id:
        return json(response_message(EINVAL, "Field team_id is required"))

    user = request.ctx.user

    team = await Team.find_one({'_id': ObjectId(team_id)})
    if not team:
        return json(response_message(ENOENT, 'Team not found'))

    if user not in team.members:
        team.members.append(user)
        await team.commit()
    if team not in user.teams:
        user.teams.append(team)
        await user.commit()

    return json(response_message(SUCCESS))

@bp.get('/users')
@doc.summary('list all users of a team')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_team_id)
@doc.produces(_user_list)
@token_required
async def handler(request):
    user = request.ctx.user

    team_id = request.args.get('team_id', None)
    if not team_id:
        return json(response_message(EINVAL, 'Field team_id is required'))

    team = await Team.find_one({'_id': ObjectId(team_id)})
    if not team:
        return json(response_message(ENOENT, 'Team not found'))

    if user not in team.members:
        if user not in team.organization.members:
            return json(response_message(EPERM, 'You are not in the organization'))

    ret = []
    for member in team.members:
        m = await member.fetch()
        ret.append({
            'value': str(m.pk),
            'label': m.name,
            'email': m.email
        })
    return json(response_message(SUCCESS, users=ret))

bp.add_route(TeamView.as_view(), '/')
