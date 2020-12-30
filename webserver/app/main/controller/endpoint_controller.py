import asyncio
import random
import urllib.parse
import uuid

from bson import ObjectId
from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json
from sanic_openapi import doc
from task_runner.runner import check_endpoint

from ..model.database import (EVENT_CODE_CANCEL_TASK, EVENT_CODE_START_TASK, QUEUE_PRIORITY,
                              QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Endpoint, Task, TaskQueue,
                              Test)
from ..util import js2python_bool, push_event
from ..util.decorator import (organization_team_required_by_args,
                              organization_team_required_by_json,
                              token_required)
from ..util.dto import EndpointDto, json_response, organization_team
from ..util.response import response_message, EACCES, SUCCESS, EINVAL, EPERM, ENOENT

_endpoint_query = EndpointDto.endpoint_query
_endpoint_list = EndpointDto.endpoint_list
_endpoint_uid = EndpointDto.endpoint_uid
_endpoint = EndpointDto.endpoint
_queuing_task_list = EndpointDto.queuing_task_list
_queuing_task = EndpointDto.queuing_task_list._queuing_task_list._queuing_tasks._queuing_task
_endpoint_online_check = EndpointDto.endpoint_online_check

bp = Blueprint('endpoint', url_prefix='/endpoint')

class EndpointView(HTTPMethodView):
    @doc.summary('get all test endpoints available')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_endpoint_query)  # TODO: bug, can't show the doc when using it like this
    @doc.produces(_endpoint_list)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        forbidden = request.args.get('forbidden', default=False)
        unauthorized = request.args.get('unauthorized', default=False)

        forbidden = js2python_bool(forbidden)
        unauthorized = js2python_bool(unauthorized)

        organization = request.ctx.organization
        team = request.ctx.team

        page = int(page)
        limit = int(limit)
        if page <= 0 or limit <= 0:
            return json(response_message(EINVAL, 'Field page and limit should be larger than 1'))

        if title:
            query = {'name': {'$regex': title}, 'organization': organization.pk, 'team': team.pk if team else None, 'status': {'$ne': 'Forbidden'}}
        else:
            query = {'organization': organization.pk, 'team': team.pk if team else None, 'status': {'$ne': 'Forbidden'}}
        if forbidden and unauthorized:
            del query['status']
            query['$or'] = [{'status': 'Forbidden'}, {'status': 'Unauthorized'}]
        else:
            if forbidden:
                query['status'] = 'Forbidden'
            if unauthorized:
                query['status'] = 'Unauthorized'

        ret = []
        async for ep in Endpoint.find(query).skip((page - 1) * limit).limit(limit):
            tests = []
            test_refs = []
            if ep.tests:
                for t in ep.tests:
                    test = await t.fetch()
                    if test.test_suite:
                        tests.append(test.test_suite)
                    else:
                        tests.append(str(test.pk))
                    test_refs.append(str(test.pk))
            ret.append({
                'name': ep.name,
                'status': ep.status,
                'enable': ep.enable,
                'last_run': ep.last_run_date.timestamp() * 1000 if ep.last_run_date else 0,
                'tests': tests,
                'test_refs': test_refs,
                'endpoint_uid': str(ep.uid)
            })
        return json(response_message(SUCCESS, endpoints=ret, total=await Endpoint.count_documents(query)))

    @doc.summary('Delete the test endpoint with the specified endpoint uid')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_endpoint_uid, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        data = request.json
        organization = request.ctx.organization
        team = request.ctx.team

        endpoint_uid = data.get('endpoint_uid', None)
        if endpoint_uid is None:
            return json(response_message(EINVAL, 'Field endpoint_uid is required'), 400)
        endpoint = await Endpoint.find_one({'uid': uuid.UUID(endpoint_uid)})
        if endpoint is None:
            return json(response_message(EINVAL, 'Endpoint not found'), 404)

        if await TaskQueue.count_documents({'endpoint': endpoint.pk, 'organization': organization.pk, 'team': team.pk if team else None}) == 0:
            await endpoint.delete()
            return json(response_message(SUCCESS))
        taskqueues = await TaskQueue.find({'endpoint': endpoint.pk, 'organization': organization.pk, 'team': team.pk if team else None})
        async for taskqueue in taskqueues:
            taskqueue.to_delete = True
            await taskqueue.commit()

        await asyncio.gather(*[q.flush(cancelled=True) for q in taskqueues])
        for q in taskqueues:
            if q.running_task:
                running_task = await q.running_task.fetch()
                message = {
                    'endpoint_uid': endpoint_uid,
                    'priority': q.priority,
                    'task_id': str(running_task.pk)
                }
                ret = await push_event(organization=organization, team=team, code=EVENT_CODE_CANCEL_TASK, message=message)
                if not ret:
                    return json(response_message(EPERM, 'Pushing the event to event queue failed'))

        ret = await push_event(organization=organization, team=team, code=EVENT_CODE_START_TASK, message={'endpoint_uid': endpoint_uid, 'to_delete': True})
        if not ret:
            return json(response_message(EPERM, 'Pushing the event to event queue failed'))

        return json(response_message(SUCCESS))

    @doc.summary('update the endpoint')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_endpoint, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def post(self, request):
        data = request.json
        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            return json(response_message(EINVAL, 'Tests is not a list'))
        uid = data.get('uid', None)
        if not uid:
            return json(response_message(EINVAL, 'Endpoint uid is invalid'))

        endpoint_tests = []
        for t in tests:
            tt = await Test.find_one({'test_suite': t, 'organization': organization.pk, 'team': team.pk if team else None})
            if not tt:
                return json(response_message(ENOENT, 'Test suite {} not found'.format(t)))
            endpoint_tests.append(tt)

        endpoint = await Endpoint.find_one({'uid': uuid.UUID(uid)})
        if not endpoint:
            return json(response_message(ENOENT, 'Endpoint not found'))
        if await TaskQueue.count_documents({'endpoint': endpoint.pk, 'organization': organization.pk, 'team': team.pk if team else None}) == 0:
            for priority in QUEUE_PRIORITY:
                taskqueue = TaskQueue(endpoint=endpoint, priority=priority, team=team, organization=organization)
                await taskqueue.commit()
        else:
            async for taskqueue in TaskQueue.find({'endpoint': endpoint.pk, 'organization': organization.pk, 'team': team.pk if team else None}):
                taskqueue.endpoint = endpoint
                await taskqueue.commit()

        endpoint.name = data.get('endpoint_name', 'test site #1')
        endpoint.enable = js2python_bool(data.get('enable', False))
        endpoint.tests = endpoint_tests
        await endpoint.commit()

        return json(response_message(SUCCESS))

class EndpointQueueView(HTTPMethodView):
    @doc.summary('get queuing tasks of an endpoint')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_endpoint_uid)
    @doc.produces(_queuing_task_list)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        organization = request.ctx.organization
        team = request.ctx.team

        query = {'organization': organization.pk, 'team': team.pk if team else None}
        endpoint_uid = request.args.get('uid', None)
        if endpoint_uid:
            endpoint = await Endpoint.find_one({'uid': uuid.UUID(endpoint_uid)})
            if not endpoint:
                return json(response_message(EINVAL, 'endpoint not found'))
            query['endpoint'] = endpoint.pk

        ret = []
        async for taskqueue in TaskQueue.find(query):
            endpoint = await taskqueue.endpoint.fetch()
            taskqueue_stat = ({
                'endpoint': endpoint.name,
                'priority': taskqueue.priority,
                'waiting': len(taskqueue.tasks) if taskqueue.tasks else 0,
                'status': endpoint.status,
                'endpoint_uid': str(endpoint.uid),
                'tasks': []
            })
            if taskqueue.running_task:
                running_task = await taskqueue.running_task.fetch()
                if running_task:
                    # assert running_task.status == 'running'
                    taskqueue_stat['tasks'].append({
                        'endpoint': endpoint.name,
                        'priority': taskqueue.priority,
                        'task': running_task.test_suite,
                        'task_id': str(running_task.pk),
                        'status': 'Running'
                    })
            if taskqueue.tasks:
                for t in taskqueue.tasks:
                    task = await t.fetch()
                    taskqueue_stat['tasks'].append({
                        'endpoint': endpoint.name,
                        'priority': task.priority,
                        'task': task.test_suite,
                        'task_id': str(task.pk),
                        'status': 'Waiting'})
            ret.append(taskqueue_stat)
        return json(response_message(SUCCESS, task_queues=ret))

    @doc.summary('update task queue of an endpoint')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(organization_team, location='body')
    @doc.consumes(doc.List(_queuing_task, name='taskqueues'), location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def post(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        taskqueues = request.json.get('taskqueues', None)
        if not taskqueues:
            return json(response_message(EINVAL, 'Field taskqueues is required'))
        if not isinstance(taskqueues, list):
            return json(response_message(EINVAL, 'Field taskqueues should be a list'))

        for taskqueue in taskqueues:
            if 'endpoint_uid' not in taskqueue or 'priority' not in taskqueue:
                return json(response_message(EINVAL, 'Task queue lacks the field endpoint_uid and field priority'))
            endpoint = await Endpoint.find_one({'uid': uuid.UUID(taskqueue['endpoint_uid'])})
            if not endpoint:
                return json(response_message(EINVAL, f"endpoint not found for uid {taskqueue['endpoint_uid']}"))
            queue = await TaskQueue.find_one({'endpoint': endpoint.pk, 'priority': taskqueue['priority'], 'team': team.pk if team else None, 'organization': organization.pk})
            if not queue:
                return json(response_message(EINVAL, 'Task queue querying failed for {} of priority {}'.format(taskqueue['endpoint_uid'], taskqueue['priority'])))

            tasks = []
            for task in taskqueue['tasks']:
                if 'task_id' not in task:
                    return json(response_message(EINVAL, 'Task lacks the field task_id'))
                if task['priority'] != taskqueue['priority']:
                    return json(response_message(EINVAL, 'task\'s priority is not equal to taskqueue\'s'))
                t = await Task.find_one({'_id': ObjectId(task['task_id'])})
                if not t:
                    return json(response_message(ENOENT, 'task not found for ' + task['task_id']))
                tasks.append(t)

            if not await queue.flush():
                return json(response_message(EPERM, 'task queue {} {} flushing failed'.format(endpoint.uid, queue.priority)))

            await queue.acquire_lock()
            set1 = set(tasks)
            set2 = set(queue.tasks)
            task_cancel_set = set2 - set1
            for task in task_cancel_set:
                task.status = 'cancelled'
                await task.commit()
            await queue.release_lock()

            for task in tasks:
                # no need to lock task as task queue has been just flushed, no runner is supposed to hold it yet
                if task.status == 'waiting':
                    if not await queue.push(task):
                        logger.error('pushing the task {} to task queue timed out'.format(str(task.pk)))
                        return json(response_message(EACCES, 'failed to push the task to task queue'))
            return json(response_message(SUCCESS))

@bp.post('/check')
@doc.summary('check whether endpoint is online')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_endpoint_uid, location='body')
@doc.produces(_endpoint_online_check)
@token_required
@organization_team_required_by_json
async def handler(request):
    organization = request.ctx.organization
    team = request.ctx.team

    endpoint_uid = request.json.get('endpoint_uid', None)
    if endpoint_uid is None:
        return json(response_message(EINVAL, 'Field endpoint_uid is required'))

    ret = await check_endpoint(request.app, uuid.UUID(endpoint_uid), organization, team)
    if not ret:
        return json(response_message(SUCCESS, 'Endpoint offline', status=False))
    else:
        return json(response_message(SUCCESS, 'Endpoint online', status=True))

@bp.post('/authorize')
@doc.summary('authorize the test endpoint')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_endpoint_uid, location='body')
@doc.produces(json_response)
@token_required
@organization_team_required_by_json
async def handler(request):
    data = request.json
    organization = request.ctx.organization
    team = request.ctx.team

    endpoint_uid = data.get('endpoint_uid', None)
    if endpoint_uid is None:
        return json(response_message(EINVAL, 'Field endpoint_uid is required'))
    endpoint = await Endpoint.find_one({'uid': uuid.UUID(endpoint_uid)})

    if not endpoint:
        endpoint = Endpoint(name=f'Test Site {random.randint(1, 9999)}', uid=endpoint_uid, organization=organization, status='Offline')
        if team:
            endpoint.team = team
        await endpoint.commit()
    else:
        endpoint.name = f'Test Site {random.randint(1, 9999)}'
        endpoint.status = 'Offline'
        await endpoint.commit()

    if await TaskQueue.count_documents({'endpoint': endpoint.pk, 'team': team.pk if team else None, 'organization': organization.pk}) == 0:
        for priority in QUEUE_PRIORITY:
            taskqueue = TaskQueue(endpoint=endpoint, priority=priority, organization=organization)
            if team:
                taskqueue.team = team
            await taskqueue.commit()
    else:
        async for taskqueue in TaskQueue.find({'endpoint': endpoint.pk, 'team': team.pk if team else None, 'organization': organization.pk}):
            taskqueue.endpoint = endpoint
            await taskqueue.commit()

    # await check_endpoint(request.app, uuid.UUID(endpoint_uid), organization, team)

    return json(response_message(SUCCESS))

@bp.post('/forbid')
@doc.summary('forbid the test endpoint so that it won\'t show in the endpoint querying results')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_endpoint_uid, location='body')
@doc.produces(json_response)
@token_required
@organization_team_required_by_json
async def handler(request):
    data = request.json
    organization = request.ctx.organization
    team = request.ctx.team

    endpoint_uid = data.get('endpoint_uid', None)
    if endpoint_uid is None:
        return json(response_message(EINVAL, 'Field endpoint_uid is required'))

    endpoint = await Endpoint.find_one({'uid': uuid.UUID(endpoint_uid)})
    if not endpoint:
        endpoint = Endpoint(uid=endpoint_uid, organization=organization, status='Forbidden')
        if team:
            endpoint.team = team
        await endpoint.commit()
    else:
        endpoint.status = 'Forbidden'
        await endpoint.commit()

    return json(response_message(SUCCESS))

@bp.get('/config')
@doc.summary('get the endpoint\'s configuration')
@doc.consumes(_endpoint_uid)
# @doc.produces(_endpoint_config) #TODO
@token_required
@organization_team_required_by_args
def handler(request):
    organization = request.ctx.organization
    team = request.ctx.team

    endpoint_uid = request.args.get('uuid', None)
    if endpoint_uid is None:
        return json(response_message(EINVAL, 'Field endpoint_uid is required'))

    return json(response_message(SUCCESS, 'Config is not implemented'))

bp.add_route(EndpointView.as_view(), '/')
bp.add_route(EndpointQueueView.as_view(), '/queue')
