from flask import request
from flask_restplus import Resource

from ..model.database import (QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Task, TaskQueue, Test, Endpoint)
from ..util.dto import EndpointDto

api = EndpointDto.api

@api.route('/')
class EndpointController(Resource):
    @api.doc('get all test endpoints available')
    def get(self):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)

        page = int(page)
        limit = int(limit)

        query = []
        if title:
            query.append({'name__contains': title})
            query.append({'endpoint_address__contains': title})
        query.append({})

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

    @api.doc('delete the test endpoint with the specified address')
    def delete(self):
        address = request.args.get('address', default=None)
        if address is None:
            print('parameter address is required')
            api.abort(404)

        for taskqueue in TaskQueue.objects(endpoint_address=address):
            taskqueue.delete()

        if address:
            ep = Endpoint.objects(endpoint_address=address)
            if ep:
                ep.delete()

    @api.doc('create a task queue for the endpoint address')
    def post(self):
        data = request.json

        endpoint_address = data.get('endpoint_address', None)
        if endpoint_address is None or endpoint_address == '':
            print('field endpoint_address is required')
            api.abort(404)

        try:
            endpoint = Endpoint.objects(endpoint_address=endpoint_address).get()
        except Endpoint.MultipleObjectsReturned:
            print('multiple endpoints exists')
            api.abort(404)
        except Endpoint.DoesNotExist:
            endpoint = Endpoint()
            endpoint.endpoint_address = endpoint_address
            endpoint.save()
            try:
                taskqueue = TaskQueue.objects(endpoint_address=endpoint_address).get()
            except TaskQueue.MultipleObjectsReturned:
                print('a task queues exists')
                api.abort(404)
            except TaskQueue.DoesNotExist:
                for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
                    taskqueue = TaskQueue(endpoint_address=endpoint_address, priority=priority)
                    taskqueue.endpoint = endpoint
                    taskqueue.save()
            else:
                print('a task queue exists')
                api.abort(404)

        endpoint.name = data.get('endpoint_name', endpoint_address)
        endpoint.enable = data.get('enable', False)

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            print('tests is not a list')
            api.abort(404)
        endpoint.tests = []
        for t in tests:
            try:
                tt = Test.objects(test_suite=t).get()
            except Test.DoesNotExist:
                print('test suite {} not found'.format(t))
                api.abort(404)
            else:
                endpoint.tests.append(tt)
        endpoint.save()

        return {'status': 0}

@api.route('/queue/')
class EndpointController(Resource):
    @api.doc('get queuing tasks of an endpoint')
    def get(self):
        query = {}
        address = request.args.get('address', default=None)
        if address:
            query = {'endpoint_address': address}

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

    @api.doc('update task queue of an endpoint')
    def post(self):
        taskqueues = request.json

        for taskqueue in taskqueues:
            if 'address' not in taskqueue or 'priority' not in taskqueue:
                print('task queue lacks the field address and field priority')
                api.abort(404)
            queue = TaskQueue.objects(endpoint_address=taskqueue['address'], priority=taskqueue['priority'])
            if queue.count() != 1:
                print('task queue querying failed for {} of priority{}'.format(taskqueue['address'], taskqueue['priority']))
                api.abort(404)

            for task in taskqueue['tasks']:
                if 'task_id' not in task:
                    print('task lacks the field task_id')
                    api.abort(404)
                if task['priority'] != taskqueue['priority']:
                    print('task\'s priority is not equal to taskqueue\'s')
                    api.abort(404)
                try:
                    t = Task.objects(pk=task['task_id']).get()
                except Task.DoesNotExist:
                    print('task not found for ' + task['task_id'])
                    api.abort(404)

            q = queue[0]
            if not q.flush(q.endpoint_address, q.priority):
                print('task queue {} {} flushing failed'.format(q.endpoint_address, q.priority))
                api.abort(404)
                break

            for task in taskqueue['tasks']:
                # no need to lock task as task queue has been just flushed, no runner is supposed to hold it yet
                t = Task.objects(pk=task['task_id']).get()
                if t.status == 'waiting':
                    if not q.push(t, q.endpoint_address, q.priority):
                        print('pushing the task to task queue timed out')
                        api.abort(404)
