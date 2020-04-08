import random
import urllib.parse
import uuid
from flask import request, current_app
from flask_restx import Resource
from mongoengine import ValidationError
from mongoengine.queryset.visitor import Q

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json
from task_runner.runner import check_endpoint

from ..model.database import *
from ..util.dto import EndpointDto
from ..util.response import *
from ..util import push_event

api = EndpointDto.api
_endpoint_list = EndpointDto.endpoint_list
_endpoint_del = EndpointDto.endpoint_del
_endpoint = EndpointDto.endpoint
_queuing_tasks = EndpointDto.queuing_tasks
_queue_update = EndpointDto.queue_update

@api.route('/')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get all test endpoints')
    @api.param('organization', description='The organization ID')
    @api.param('team', description='The team ID')
    @api.param('page', default=1, description='The page number of the whole test report list')
    @api.param('limit', default=10, description='The item number of a page')
    @api.param('title', description='The test suite name')
    @api.marshal_list_with(_endpoint_list)
    def get(self, **kwargs):
        """Get all test endpoints available"""
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        forbidden = request.args.get('forbidden', default=False)
        unauthorized = request.args.get('unauthorized', default=False)

        forbidden = True if forbidden == 'true' else False
        unauthorized = True if unauthorized == 'true' else False

        organization = kwargs['organization']
        team = kwargs['team']

        page = int(page)
        limit = int(limit)

        if title:
            query = {'name__contains': title, 'organization': organization, 'team': team, 'status__not__exact': 'Forbidden'}
        else:
            query = {'organization': organization, 'team': team, 'status__not__exact': 'Forbidden'}
        if forbidden:
            query = {'status': 'Forbidden'}
        if unauthorized:
            query = {'status': 'Unauthorized'}
        if forbidden and unauthorized:
            query = Q(status='Forbidden') | Q(status='Unauthorized')
            endpoints = Endpoint.objects(query)
        else:
            endpoints = Endpoint.objects(**query)

        ret = []
        for ep in endpoints:
            tests = []
            for t in ep.tests:
                if hasattr(t, 'test_suite'):
                    tests.append(t.test_suite)
                else:
                    tests.append(str(t.id))
            ret.append({
                'name': ep.name,
                'status': ep.status,
                'enable': ep.enable,
                'last_run': ep.last_run_date.timestamp() * 1000 if ep.last_run_date else 0,
                'tests': tests,
                'test_refs': [str(t.id) for t in ep.tests],
                'endpoint_uid': ep.uid
            })
        return {'items': ret[(page-1)*limit:page*limit], 'total': len(ret)}

    @token_required
    @organization_team_required_by_json
    @api.doc('delete the test endpoint')
    @api.expect(_endpoint_del)
    def delete(self, **kwargs):
        """Delete the test endpoint with the specified endpoint uid"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']

        endpoint_uid = data.get('endpoint_uid', None)
        if endpoint_uid is None:
            return response_message(EINVAL, 'Field endpoint_uid is required'), 400
        endpoint = Endpoint.objects(uid=endpoint_uid).first()
        if endpoint is None:
            return response_message(EINVAL, 'Endpoint not found'), 404

        taskqueues = TaskQueue.objects(endpoint=endpoint, organization=organization, team=team)
        if taskqueues.count() == 0:
            endpoint.delete()
            return response_message(SUCCESS)
        taskqueues.update(to_delete=True)

        for q in taskqueues:
            q.flush(cancelled=True)
            if q.running_task:
                message = {
                    'endpoint_uid': endpoint_uid,
                    'priority': q.priority,
                    'task_id': str(q.running_task.id)
                }
                ret = push_event(organization=organization, team=team, code=EVENT_CODE_CANCEL_TASK, message=message)
                if not ret:
                    return response_message(EPERM, 'Pushing the event to event queue failed'), 403

        ret = push_event(organization=organization, team=team, code=EVENT_CODE_START_TASK, message={'endpoint_uid': endpoint_uid, 'to_delete': True})
        if not ret:
            return response_message(EPERM, 'Pushing the event to event queue failed'), 403

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('update the endpoint')
    @api.expect(_endpoint)
    def post(self, **kwargs):
        """Update the endpoint"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            return response_message(EINVAL, 'Tests is not a list'), 400
        uid = data.get('uid', None)
        if not uid:
            return response_message(EINVAL, 'Endpoint uid is invalid'), 400

        endpoint_tests = []
        for t in tests:
            tt = Test.objects(test_suite=t, organization=organization, team=team).first()
            if not tt:
                return response_message(ENOENT, 'Test suite {} not found'.format(t)), 404
            endpoint_tests.append(tt)

        endpoint = Endpoint.objects(uid=uid).first()
        if not endpoint:
            return response_message(ENOENT, 'Endpoint not found'), 404
        taskqueues = TaskQueue.objects(endpoint=endpoint, team=team, organization=organization)
        if taskqueues.count() == 0:
            for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
                taskqueue = TaskQueue(endpoint=endpoint, priority=priority, team=team, organization=organization)
                taskqueue.save()
        else:
            taskqueues.update(endpoint=endpoint)

        endpoint.name = data.get('endpoint_name', 'test site#1')
        endpoint.enable = data.get('enable', False)
        endpoint.tests = endpoint_tests
        endpoint.save()

        return response_message(SUCCESS), 200

@api.route('/queue/')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get queuing tasks')
    @api.param('organization', description='The organization ID')
    @api.param('team', description='The team ID')
    @api.param('uid', description='The endpoint uid')
    @api.marshal_list_with(_queuing_tasks)
    def get(self, **kwargs):
        """Get the queuing tasks of an endpoint"""
        organization = kwargs['organization']
        team = kwargs['team']

        query = {'organization': organization, 'team': team}
        endpoint_uid = request.args.get('uid', default=None)
        if endpoint_uid:
            query['endpoint_uid'] = endpoint_uid

        ret = []
        for taskqueue in TaskQueue.objects(**query):
            taskqueue_stat = ({
                'endpoint': taskqueue.endpoint.name,
                'priority': taskqueue.priority,
                'waiting': len(taskqueue.tasks),
                'status': taskqueue.endpoint.status,
                'endpoint_uid': taskqueue.endpoint.uid,
                'tasks': []
            })
            if taskqueue.running_task and taskqueue.running_task.status == 'running':
                taskqueue_stat['tasks'].append({
                    'endpoint': taskqueue.endpoint.name,
                    'priority': taskqueue.priority,
                    'task': taskqueue.running_task.test_suite,
                    'task_id': str(taskqueue.running_task.id),
                    'status': 'Running'
                })
            for task in taskqueue.tasks:
                taskqueue_stat['tasks'].append({
                    'endpoint': taskqueue.endpoint.name,
                    'priority': task.priority,
                    'task': task.test_suite,
                    'task_id': str(task.id),
                    'status': 'Waiting'})
            ret.append(taskqueue_stat)
        return ret

    @token_required
    @organization_team_required_by_json
    @api.doc('update task queue')
    @api.expect(_queue_update)
    def post(self, **kwargs):
        """Update the task queue of an endpoint"""
        organization = kwargs['organization']
        team = kwargs['team']
        taskqueues = request.json.get('taskqueues', None)
        if not taskqueues:
            return response_message(EINVAL, 'Field taskqueues is required'), 400
        if not isinstance(taskqueues, list):
            return response_message(EINVAL, 'Field taskqueues should be a list'), 400

        for taskqueue in taskqueues:
            if 'endpoint_uid' not in taskqueue or 'priority' not in taskqueue:
                return response_message(EINVAL, 'Task queue lacks the field endpoint_uid and field priority'), 400
            endpoint = Endpoint.objects(uid=taskqueue['endpoint_uid']).first()
            if not endpoint:
                return response_message(EINVAL, f"endpoint not found for uid {taskqueue['endpoint_uid']}"), 400
            queue = TaskQueue.objects(endpoint=endpoint, priority=taskqueue['priority'], team=team, organization=organization).first()
            if not queue:
                return response_message(EINVAL, 'Task queue querying failed for {} of priority {}'.format(taskqueue['endpoint_uid'], taskqueue['priority'])), 400

            tasks = []
            for task in taskqueue['tasks']:
                if 'task_id' not in task:
                    return response_message(EINVAL, 'Task lacks the field task_id'), 400
                if task['priority'] != taskqueue['priority']:
                    return response_message(EINVAL, 'task\'s priority is not equal to taskqueue\'s'), 400
                t = Task.objects(pk=task['task_id']).first()
                if not t:
                    return response_message(ENOENT, 'task not found for ' + task['task_id']), 404
                tasks.append(t)

            if not queue.flush():
                return response_message(EPERM, 'task queue {} {} flushing failed'.format(queue.endpoint.uid, queue.priority)), 401

            queue.acquire_lock()
            set1 = set(tasks)
            set2 = set(queue.tasks)
            task_cancel_set = set2 - set1
            for task in task_cancel_set:
                task.update(status='cancelled')
            queue.release_lock()

            for task in tasks:
                # no need to lock task as task queue has been just flushed, no runner is supposed to hold it yet
                if task.status == 'waiting':
                    if not queue.push(task):
                        current_app.logger.error('pushing the task {} to task queue timed out'.format(str(task.id)))

@api.route('/check/')
class EndpointChecker(Resource):
    @token_required
    @organization_team_required_by_json
    @api.doc('check whether endpoint is online')
    @api.expect(_endpoint_del)
    def post(self, **kwargs):
        """Update the task queue of an endpoint"""
        organization = kwargs['organization']
        team = kwargs['team']

        endpoint_uid = request.json.get('endpoint_uid', None)
        if endpoint_uid is None:
            return response_message(EINVAL, 'Field endpoint_uid is required'), 400

        ret = check_endpoint(current_app._get_current_object(), endpoint_uid, organization, team)
        if not ret:
            return response_message(SUCCESS, 'Endpoint offline', status=False), 200
        else:
            return response_message(SUCCESS, 'Endpoint online', status=True), 200

@api.route('/authorize')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_json
    @api.doc('authorize the test endpoint')
    @api.expect(_endpoint_del)
    def post(self, **kwargs):
        """Authorize the test endpoint with the specified endpoint uid"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']

        endpoint_uid = data.get('endpoint_uid', None)
        if endpoint_uid is None:
            return response_message(EINVAL, 'Field endpoint_uid is required'), 400
        endpoint = Endpoint.objects(uid=endpoint_uid).first()

        if not endpoint:
            endpoint = Endpoint(name=f'Test Site {random.randint(1, 9999)}', uid=endpoint_uid, organization=organization, team=team, status='Offline')
            endpoint.save()
        else:
            endpoint.modify(name=f'Test Site {random.randint(1, 9999)}', status='Offline')

        taskqueues = TaskQueue.objects(endpoint=endpoint, team=team, organization=organization)
        if taskqueues.count() == 0:
            for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
                taskqueue = TaskQueue(endpoint=endpoint, priority=priority, team=team, organization=organization)
                taskqueue.save()
        else:
            taskqueues.update(endpoint=endpoint)

        check_endpoint(current_app._get_current_object(), endpoint_uid, organization, team)

        return response_message(SUCCESS)

@api.route('/forbid')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_json
    @api.doc('forbid the test endpoint')
    @api.expect(_endpoint_del)
    def post(self, **kwargs):
        """Forbid the test endpoint with the specified endpoint uid"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']

        endpoint_uid = data.get('endpoint_uid', None)
        if endpoint_uid is None:
            return response_message(EINVAL, 'Field endpoint_uid is required'), 400
        endpoint = Endpoint.objects(uid=endpoint_uid).first()

        if not endpoint:
            endpoint = Endpoint(uid=endpoint_uid, organization=organization, team=team, status='Forbidden')
            endpoint.save()
        else:
            endpoint.update(status='Forbidden')

        return response_message(SUCCESS)
