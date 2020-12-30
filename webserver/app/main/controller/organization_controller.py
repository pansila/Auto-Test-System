import aiofiles
import base64
import os
from pathlib import Path
from bson import ObjectId
from sanic_openapi import doc
from sanic.response import json, file
from sanic import Blueprint
from sanic.views import HTTPMethodView
from async_files.utils import async_wraps

from ..util import async_rmtree
from ..util.decorator import token_required
from ..model.database import Organization, Team, User, Test, Task, TaskQueue, TestResult

from ..service.auth_helper import Auth
from ..util.dto import OrganizationDto, json_response, organization_team
from ..util.response import response_message, SUCCESS, USER_NOT_EXIST, EPERM, ENOENT, EINVAL, EEXIST
from ..config import get_config
from ..util.identicon import render_identicon

USERS_ROOT = Path(get_config().USERS_ROOT)

_user_list = OrganizationDto.user_list
_organization_list = OrganizationDto.organization_list
_new_organization = OrganizationDto.new_organization
_organization_id = OrganizationDto.organization_id
_organization_team_list = OrganizationDto.organization_team_list
_transfer_ownership = OrganizationDto.transfer_ownership
_organization_avatar = OrganizationDto.organization_avatar


bp = Blueprint('organization', url_prefix='/organization')

class OrganizationView(HTTPMethodView):
    @doc.summary('List all organizations joined by the logged in user')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.produces(_organization_list)
    @token_required
    async def get(self, request):
        ret = []
        check = []
        user = request.ctx.user

        async for organization in Organization.find({'owner': user.pk}):
            owner = await organization.owner.fetch()
            ret.append({
                'label': organization.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'personal': organization.personal,
                'value': str(organization.pk)
            })
            check.append(organization)

        for organization in user.organizations:
            if organization in check:
                continue
            owner = await organization.owner.fetch()
            ret.append({
                'label': organization.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'personal': organization.personal,
                'value': str(organization.pk)
            })

        ret.sort(key=lambda x: not x['personal'])

        return json(response_message(SUCCESS, organizations=ret))

    @doc.summary('create a new organization')
    @doc.description('The logged in user performing the operation will become the owner of the organization')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(doc.String(name='name', description="new organization\'s name"), location='body')
    @doc.produces(json_response)
    @token_required
    async def post(self, request):
        data = request.json
        name = data.get('name', None)
        if not name:
            return json(response_message(EINVAL, 'Field name is required'))
        
        user = request.ctx.user

        org = Organization(name=name)
        org.owner = user
        org.members.append(user)
        await org.commit()
        user.organizations.append(org)
        await user.commit()

        org.path = name + '#' + str(org.pk)
        org_root = USERS_ROOT / org.path
        try:
            await aiofiles.os.mkdir(org_root)
        except FileExistsError as e:
            return json(response_message(EEXIST))

        img = await render_identicon(hash(name), 27)
        await async_wraps(img.save)(org_root / ('%s.png' % org.pk))
        org.avatar = f'{org.pk}.png' 
        await org.commit()

        return json(response_message(SUCCESS))

    @doc.summary('delete an organization')
    @doc.description('Only the owner of the organization could perform this operation')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_organization_id, location='body')
    @doc.produces(json_response)
    @token_required
    async def delete(self, request):
        organization_id = request.json.get('organization_id', None)
        if not organization_id:
            return json(response_message(EINVAL, "Field organization_id is required"))

        organization = await Organization.find_one({'_id': ObjectId(organization_id)})
        if not organization:
            return json(response_message(ENOENT, "Team not found"))

        user = request.ctx.user
        if await organization.owner.fetch() != user:
            return json(response_message(EINVAL, 'You are not the organization owner'))

        try:
            await async_rmtree(USERS_ROOT / organization.path)
        except FileNotFoundError:
            pass

        user.organizations.remove(organization)
        await user.commit()

        # Tests belong to teams of the organization will be deleted as well by this query
        async for test in Test.find({'organization': organization.pk}):
            async for task in Task.find({'test': test.pk}):
                async for tr in TestResult.find({'task': task.pk}):
                    await tr.delete()
                await task.delete()
            await test.delete()
        async for queue in TaskQueue.find({'organization': organization.pk}):
            queue.to_delete = True
            queue.organization = None
            queue.team = None
            await queue.commit()
        
        async for team in Team.find({'organization': organization.pk}):
            async for user in User.find():
                user.teams.remove(team)
                await User.commit()
            await team.delete()

        await organization.delete()

        return json(response_message(SUCCESS))

@bp.get('/avatar/<org_id>')
@doc.summary('get the avatar of an organization')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(_organization_avatar)
@token_required
async def handler(request, org_id):
    user = request.ctx.user
    org = await Organization.find_one({'_id': ObjectId(org_id)})
    if org:
        if user not in org.members:
            return json(response_message(EPERM), 'You are not a member of the organization')
        if org.avatar:
            async with aiofiles.open(USERS_ROOT / org.path / org.avatar, 'rb') as img:
                _, ext = os.path.splitext(org.avatar)
                return json(response_message(SUCCESS, type=f'image/{ext[1:]}', data=base64.b64encode(await img.read()).decode('ascii')))
        else:
            owner = await org.owner.fetch()
            async with aiofiles.open(USERS_ROOT / org.path / owner.avatar, 'rb') as img:
                _, ext = os.path.splitext(owner.avatar)
                return json(response_message(SUCCESS, type=f'image/{ext[1:]}', data=base64.b64encode(await img.read()).decode('ascii')))
    return json(response_message(ENOENT, 'Organization not found'))

@bp.delete('/member')
@doc.summary('let current logged in user quit the organization')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_organization_id, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    organization_id = request.json.get('organization_id', None)
    if not organization_id:
        return json(response_message(EINVAL, "Field organization_id is required"))

    org_to_quit = await Organization.find_one({'_id': ObjectId(organization_id)})
    if not org_to_quit:
        return json(response_message(ENOENT, "Organization not found"))

    user = request.ctx.user

    for organization in user.organizations:
        if organization != org_to_quit:
            continue
        if await organization.owner.fetch() == user:
            return json(response_message(EPERM, "Can't quit the organization as you are the owner"))
        organization.members.remove(user)
        await organization.commit()
        user.organizations.remove(organization)
        await user.commit()
        return json(response_message(SUCCESS))
    else:
        return json(response_message(EINVAL, "User is not in the organization"))

@bp.get('/all')
@doc.summary('list all organizations registered')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(_organization_list)
@token_required
async def handler(request):
    ret = []

    async for organization in Organization.find():
        if organization.name == 'Personal':
            continue
        owner = await organization.owner.fetch()
        ret.append({
            'label': organization.name,
            'owner': owner.name,
            'owner_email': owner.email,
            'personal': organization.personal,
            'value': str(organization.pk)
        })
    return json(response_message(SUCCESS, organizations=ret))

@bp.get('/include_team')
@doc.summary('list all organizations and teams registered')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(_organization_team_list)
@token_required
async def handler(request):
    ret = []
    check = []
    user = request.ctx.user

    async for organization in Organization.find({'owner': user.pk}):
        owner = await organization.owner.fetch()
        r = {
            'label': organization.name,
            'owner': owner.name,
            'owner_email': owner.email,
            'personal': organization.personal,
            'value': str(organization.pk)
        }
        ret.append(r)
        check.append(organization)
        try:
            if not organization.team:
                continue
        except AttributeError:
            continue
        if len(organization.teams) > 0:
            r['children'] = []
        for team in organization.teams:
            owner = await team.owner.fetch()
            r['children'].append({
                'label': team.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'value': str(team.pk)
            })

    for organization in user.organizations:
        if organization in check:
            continue
        owner = await organization.owner.fetch()
        r = {
            'label': organization.name,
            'owner': owner.name,
            'owner_email': owner.email,
            'personal': organization.personal,
            'value': str(organization.pk)
        }
        ret.append(r)
        if not 'teams' in organization:
            continue
        if len(organization.teams) > 0:
            r['children'] = []
        for team in organization.teams:
            owner = await team.owner.fetch()
            r['children'].append({
                'label': team.name,
                'owner': owner.name,
                'owner_email': owner.email,
                'value': str(team.pk)
            })

    return json(response_message(SUCCESS, organization_team=ret))

@bp.post('/join')
@doc.summary('join an organization')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_organization_id, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    org_id = request.json.get('organization_id', None)
    if not org_id:
        return json(response_message(EINVAL, "Field organization_id is required"))

    user = request.ctx.user

    organization = await Organization.find_one({'_id': ObjectId(org_id)})
    if not organization:
        return json(response_message(ENOENT, 'Organization not found'))

    if user not in organization.members:
        organization.members.append(user)
        await organization.commit()
    if organization not in user.organizations:
        user.organizations.append(organization)
        await user.commit()

    return json(response_message(SUCCESS))

@bp.get('/users')
@doc.summary('list all users of an organization')
@doc.description('Note: Users in a team of the organization will not be counted')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_organization_id)
@doc.produces(_user_list)
@token_required
async def handler(request):
    user = request.ctx.user

    organization_id = request.args.get('organization_id', None)
    if not organization_id:
        return json(response_message(EINVAL, 'Field organization_id is required'))

    organization = await Organization.find_one({'_id': ObjectId(organization_id)})
    if not organization:
        return json(response_message(ENOENT, 'Organization not found'))

    if user not in organization.members:
        return json(response_message(EPERM, 'You are not in the organization'))

    ret = []
    for member in organization.members:
        m = await member.fetch()
        ret.append({
            'value': str(m.pk),
            'label': m.name,
            'email': m.email
        })
    return json(response_message(SUCCESS, users=ret))

@bp.get('/all_users')
@doc.summary('list all users')
@doc.description('Note: All Users in the organization and the organization\'s teams will be counted')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_organization_id)
@doc.produces(_user_list)
@token_required
async def handler(request):
    user = request.ctx.user

    organization_id = request.args.get('organization_id', None)
    if not organization_id:
        return json(response_message(EINVAL, 'Field organization_id is required'))

    organization = await Organization.find_one({'_id': ObjectId(organization_id)})
    if not organization:
        return json(response_message(ENOENT, 'Organization not found'))

    for member in organization.members:
        m = await member.fetch()
        if user == m:
            break
    else:
        return json(response_message(EPERM, 'You are not in the organization'))

    ret = []
    check_list = []
    for member in organization.members:
        m = await member.fetch()
        check_list.append(m)
        ret.append({'value': str(m.pk), 'label': m.name, 'email': m.email})

    for team in organization.teams:
        for user in team.members:
            u = await user.fetch()
            user_id = str(u.pk)
            if u not in check_list:
                ret.append({'value': user_id, 'label': u.name, 'email': u.email})
                check_list.append(u)

    return json(response_message(SUCCESS, users=ret))

@bp.post('/transfer')
@doc.summary('transfer ownership of an organization')
@doc.description('The new owner should have joined the organization or a team of the organization')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_transfer_ownership, location='body')
@doc.produces(json_response)
@token_required
async def handler(request):
    user = request.ctx.user

    organization_id = request.json.get('organization_id', None)
    if not organization_id:
        return json(response_message(EINVAL, 'Field organization_id is required'))

    organization = await Organization.find_one({'_id': ObjectId(organization_id)})
    if not organization:
        return json(response_message(ENOENT, 'Organization not found'))

    if await organization.owner.fetch() != user:
        return json(response_message(EPERM, 'You are not the organization owner'))

    owner_id = request.json.get('new_owner', None)
    if not owner_id:
        return json(response_message(EINVAL, 'Field new_owner is required'))

    owner = await User.find_one({'_id': ObjectId(owner_id)})
    if not owner:
        return json(response_message(ENOENT, 'New owner not found'))

    if owner not in organization.members:
        for team in organization.teams:
            if owner in team.members:
                break
        else:
            return json(response_message(EPERM, 'New owner should be a member of the organization'))

    organization.owner = owner
    if owner not in organization.members:
        organization.members.append(owner)
    await organization.commit()

    for team in organization.teams:
        if team.owner == user:
            team.owner = owner
            if owner not in team.members:
                team.members.append(owner)
            await team.commit()
    return json(response_message(SUCCESS))

bp.add_route(OrganizationView.as_view(), '/')
