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
        ret = []
        for ep in Endpoint.objects({}):
            ret.append({'address': ep.endpoint_address, 'tests': [t.test_suite for t in ep.tests]})
        return ret

    @api.response(201, 'Endpoint address successfully created.')
    @api.doc('create a task queue for the endpoint address')
    def post(self):
        data = request.json

        endpoint_address = data.get('endpoint_address', None)
        if endpoint_address is None:
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

        tests = data.get('tests', [])
        if not isinstance(tests, list):
            print('tests is not a list')
            api.abort(404)
        for t in tests:
            try:
                tt = Test.objects(test_suite=t).get()
            except Test.DoesNotExist:
                print('specified test suite {} does not exist'.format(t))
                api.abort(404)
            else:
                endpoint.tests.append(tt)
        endpoint.save()

        return {'status': 0}
