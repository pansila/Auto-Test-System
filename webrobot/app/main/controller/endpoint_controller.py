from flask import request
from flask_restplus import Resource

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json
from task_runner.runner import start_threads

from ..model.database import *
from ..util.dto import EndpointDto
from ..util.errors import *

api = EndpointDto.api

@api.route('/')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get all test endpoints available')
    def get(self, **kwargs):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)

        organization = kwargs['organization']
        team = kwargs['team']

        page = int(page)
        limit = int(limit)

        query = []
        if title:
            query.append({'name__contains': title, 'organization': organization})
            query.append({'endpoint_address__contains': title, 'organization': organization})
        else:
            query.append({'organization': organization})

        ret = []
        for q in query:
            if team:
                q['team'] = team
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
    @api.doc('delete the test endpoint with the specified address')
    @organization_team_required_by_json
    def delete(self, **kwargs):
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']

        address = data.get('address', None)
        if address is None:
            return error_message(EINVAL, 'Parameter address is required'), 400

        ret = TaskQueue.find(endpoint_address=address, organization=organization, team=team)
        if not ret:
            return error_message(ENOENT, 'Task queue not found'), 404
        taskqueues, _ = ret
        taskqueues.update(to_delete=True)

        return error_message(SUCCESS)

    @token_required
    @api.doc('create a task queue for the endpoint address')
    @organization_team_required_by_json
    def post(self, **kwargs):
        data = request.json
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        endpoint_address = data.get('endpoint_address', None)
        if not endpoint_address:
            return error_message(EINVAL, 'Field endpoint_address is required'), 400

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            return error_message(EINVAL, 'Tests is not a list'), 400

        endpoint_tests = []
        for t in tests:
            query = {'test_suite': t, 'organization': organization}
            if team:
                query['team'] = team
            tt = Test.objects(**query).first()
            if not tt:
                return error_message(ENOENT, 'Test suite {} not found'.format(t)), 404
            endpoint_tests.append(tt)

        ret = Endpoint.find(endpoint_address=endpoint_address, team=team, organization=organization)
        if not ret:
            endpoint = Endpoint(team=team, organization=organization, endpoint_address=endpoint_address)
            endpoint.save()
            ret = TaskQueue.find(endpoint_address=endpoint_address, team=team, organization=organization)
            if not ret:
                for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
                    taskqueue = TaskQueue(endpoint_address=endpoint_address, priority=priority, team=team, organization=organization)
                    taskqueue.endpoint = endpoint
                    taskqueue.save()
            else:
                return error_message(EEXIST, 'Task queues exist already'), 401
        else:
            endpoint, _ = ret

        endpoint.name = data.get('endpoint_name', endpoint_address)
        endpoint.enable = data.get('enable', False)
        endpoint.tests = endpoint_tests
        endpoint.save()

        for organization in user.organizations:
            start_threads(organization=organization)
            for team in user.teams:
                start_threads(organization=organization, team=team)

        return error_message(SUCCESS), 200

@api.route('/queue/')
class EndpointController(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get queuing tasks of an endpoint')
    def get(self, **kwargs):
        organization = kwargs['organization']
        team = kwargs['team']

        query = {'organization': organization}
        if team:
            query['team'] = team
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
    @api.doc('update task queue of an endpoint')
    def post(self, user):
        taskqueues = request.json

        for taskqueue in taskqueues:
            if 'address' not in taskqueue or 'priority' not in taskqueue:
                return error_message(EINVAL, 'Task queue lacks the field address and field priority'), 400
            queue = TaskQueue.objects(endpoint_address=taskqueue['address'], priority=taskqueue['priority'])
            if queue.count() != 1:
                return error_message(EINVAL, 'Task queue querying failed for {} of priority{}'.format(taskqueue['address'], taskqueue['priority'])), 400

            for task in taskqueue['tasks']:
                if 'task_id' not in task:
                    return error_message(EINVAL, 'Task lacks the field task_id'), 400
                if task['priority'] != taskqueue['priority']:
                    return error_message(EINVAL, 'task\'s priority is not equal to taskqueue\'s'), 400
                try:
                    t = Task.objects(pk=task['task_id']).get()
                except Task.DoesNotExist as e:
                    print(e)
                    return error_message(ENOENT, 'task not found for ' + task['task_id']), 404

            q = queue[0]
            if not q.flush(q.endpoint_address, q.priority):
                return error_message(EPERM, 'task queue {} {} flushing failed'.format(q.endpoint_address, q.priority)), 401

            for task in taskqueue['tasks']:
                # no need to lock task as task queue has been just flushed, no runner is supposed to hold it yet
                t = Task.objects(pk=task['task_id']).get()
                if t.status == 'waiting':
                    if not q.push(t, q.endpoint_address, q.priority):
                        return error_message(ETIME, 'pushing the task to task queue timed out'), 408
