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
                ret.append({
                    'address': ep.endpoint_address,
                    'name': ep.name,
                    'status': ep.status,
                    'enable': ep.enable,
                    'last_run': ep.last_run_date.timestamp() * 1000 if ep.last_run_date else 0,
                    'tests': [t.test_suite for t in ep.tests],
                    'test_refs': [str(t.id) for t in ep.tests]
                })
            if len(ret) > 0:
                break
        return ret[(page-1)*limit:page*limit]

    @api.doc('delete the test endpoint with the specified address')
    def delete(self):
        address = request.args.get('address', default=None)
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
