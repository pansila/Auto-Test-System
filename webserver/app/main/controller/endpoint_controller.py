import urllib.parse
from flask import request, current_app
from flask_restx import Resource

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

        organization = kwargs['organization']
        team = kwargs['team']

        page = int(page)
        limit = int(limit)

        query = []
        if title:
            query.append({'name__contains': title, 'organization': organization, 'team': team})
            query.append({'endpoint_address__contains': title, 'organization': organization, 'team': team})
        else:
            query.append({'organization': organization, 'team': team})

        ret = []
        for q in query:
            for ep in Endpoint.objects(**q):
                tests = []
                for t in ep.tests:
                    if hasattr(t, 'test_suite'):
                        tests.append(t.test_suite)
                    else:
                        tests.append(str(t.id))
                ret.append({
                    'address': ep.endpoint_address,
                    'name': ep.name,
                    'status': ep.status,
                    'enable': ep.enable,
                    'last_run': ep.last_run_date.timestamp() * 1000 if ep.last_run_date else 0,
                    'tests': tests,
                    'test_refs': [str(t.id) for t in ep.tests]
                })
            if len(ret) > 0:
                break
        return ret[(page-1)*limit:page*limit]

    @token_required
    @organization_team_required_by_json
    @api.doc('delete the test endpoint')
    @api.expect(_endpoint_del)
    def delete(self, **kwargs):
        """Delete the test endpoint with the specified address"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']

        address = data.get('address', None)
        if address is None:
            return response_message(EINVAL, 'Parameter address is required'), 400

        taskqueues = TaskQueue.objects(endpoint_address=address, organization=organization, team=team)
        if taskqueues.count() == 0:
            return response_message(ENOENT, 'Task queue not found'), 404
        taskqueues.update(to_delete=True)

        for q in taskqueues:
            q.flush(cancelled=True)
            if q.running_task:
                message['priority'] = q.priority
                message['task_id'] = str(q.running_task.id)
                ret = push_event(organization=organization, team=team, code=EVENT_CODE_CANCEL_TASK, message=message)
                if not ret:
                    return response_message(EPERM, 'Pushing the event to event queue failed'), 403

        ret = push_event(organization=organization, team=team, code=EVENT_CODE_START_TASK, message={'address': address, 'to_delete': True})
        if not ret:
            return response_message(EPERM, 'Pushing the event to event queue failed'), 403

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('create a task queue for the endpoint address')
    @api.expect(_endpoint)
    def post(self, **kwargs):
        """Create a task queue for the endpoint address"""
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        endpoint_address = data.get('endpoint_address', None)
        if not endpoint_address:
            return response_message(EINVAL, 'Field endpoint_address is required'), 400

        endpoint_address = endpoint_address.strip()
        scheme, address = urllib.parse.splittype(endpoint_address)
        address = urllib.parse.splittype(address)

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            return response_message(EINVAL, 'Tests is not a list'), 400

        endpoint_tests = []
        for t in tests:
            tt = Test.objects(test_suite=t, organization=organization, team=team).first()
            if not tt:
                return response_message(ENOENT, 'Test suite {} not found'.format(t)), 404
            endpoint_tests.append(tt)

        endpoint = Endpoint.objects(endpoint_address=address, team=team, organization=organization).first()
        if not endpoint:
            endpoint = Endpoint(team=team, organization=organization, endpoint_address=address)
            endpoint.save()

            taskqueue = TaskQueue.objects(endpoint_address=address, team=team, organization=organization).first()
            if not taskqueue:
                for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
                    taskqueue = TaskQueue(endpoint_address=address, priority=priority, team=team, organization=organization)
                    taskqueue.endpoint = endpoint
                    taskqueue.save()
            else:
                return response_message(EEXIST, 'Task queues exist already'), 401

        endpoint.name = data.get('endpoint_name', address)
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
    @api.param('address', description='The endpoint address')
    @api.marshal_list_with(_queuing_tasks)
    def get(self, **kwargs):
        """Get the queuing tasks of an endpoint"""
        organization = kwargs['organization']
        team = kwargs['team']

        query = {'organization': organization, 'team': team}
        address = request.args.get('address', default=None)
        if address:
            query['endpoint_address'] = address

        ret = []
        for taskqueue in TaskQueue.objects(**query):
            taskqueue_stat = ({
                'endpoint': taskqueue.endpoint.name,
                'address': taskqueue.endpoint_address,
                'priority': taskqueue.priority,
                'waiting': len(taskqueue.tasks),
                'status': taskqueue.endpoint.status,
                'tasks': []
            })
            if taskqueue.running_task and taskqueue.running_task.status == 'running':
                taskqueue_stat['tasks'].append({
                    'endpoint': taskqueue.endpoint.name,
                    'address': taskqueue.endpoint_address,
                    'priority': taskqueue.priority,
                    'task': taskqueue.running_task.test_suite,
                    'task_id': str(taskqueue.running_task.id),
                    'status': 'Running'
                })
            for task in taskqueue.tasks:
                taskqueue_stat['tasks'].append({
                    'endpoint': taskqueue.endpoint.name,
                    'address': taskqueue.endpoint_address,
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
            if 'address' not in taskqueue or 'priority' not in taskqueue:
                return response_message(EINVAL, 'Task queue lacks the field address and field priority'), 400
            queue = TaskQueue.objects(endpoint_address=taskqueue['address'], priority=taskqueue['priority'], team=team, organization=organization).first()
            if not queue:
                return response_message(EINVAL, 'Task queue querying failed for {} of priority{}'.format(taskqueue['address'], taskqueue['priority'])), 400

            for task in taskqueue['tasks']:
                if 'task_id' not in task:
                    return response_message(EINVAL, 'Task lacks the field task_id'), 400
                if task['priority'] != taskqueue['priority']:
                    return response_message(EINVAL, 'task\'s priority is not equal to taskqueue\'s'), 400
                t = Task.objects(pk=task['task_id']).first()
                if not t:
                    return response_message(ENOENT, 'task not found for ' + task['task_id']), 404

            if not queue.flush():
                return response_message(EPERM, 'task queue {} {} flushing failed'.format(queue.endpoint_address, queue.priority)), 401

            for task in taskqueue['tasks']:
                # no need to lock task as task queue has been just flushed, no runner is supposed to hold it yet
                t = Task.objects(pk=task['task_id']).first()
                if t.status == 'waiting':
                    if not queue.push(t):
                        current_app.logger.error('pushing the task to task queue timed out')

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

        address = request.json.get('address', None)
        if address is None:
            return response_message(EINVAL, 'Parameter address is required'), 400

        address = address.strip()
        scheme, address = urllib.parse.splittype(address)
        address = urllib.parse.splittype(address)

        ret = check_endpoint(current_app._get_current_object(), address, organization, team)
        if not ret:
            return response_message(SUCCESS, 'Endpoint offline', status=False), 200
        else:
            return response_message(SUCCESS, 'Endpoint online', status=True), 200
