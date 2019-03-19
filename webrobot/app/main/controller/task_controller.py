from flask import request
from flask_restplus import Resource
from mongoengine import ValidationError

from ..util.dto import TaskDto
from ..model.database import Test, Task, TaskQueue, QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX

api = TaskDto.api

@api.route('/<test_suite>')
@api.param('test_suite', 'test suite to handle')
class TaskController(Resource):
    @api.response(404, 'test suite not found.')
    def get(self, test_suite):
        if test_suite == None or test_suite == "":
            return list(Test.objects({}))
        else:
            api.abort(404)

    @api.response(201, 'Test suite successfully ran.')
    @api.doc('run a test suite')
    def post(self, test_suite):
        try:
            test = Test.objects(test_suite=test_suite).get()
        except Test.DoesNotExist:
            api.abort(404)

        task = Task()
        data = request.json
        if data is None:
            # TODO: endpoint collection
            task.endpoint_list = ['127.0.0.1:8270']
            task.priority = QUEUE_PRIORITY_DEFAULT
        elif 'endpoint_list' not in data:
            api.abort(404)
        else:
            task.endpoint_list = data['endpoint_list']

            task.priority = data.get('priority', QUEUE_PRIORITY_DEFAULT)
            if task.priority < QUEUE_PRIORITY_MIN or task.priority > QUEUE_PRIORITY_MAX:
                api.abort(404)

            task.variables = data.get('variables', {})
            if not isinstance(task.variables, dict):
                api.abort(404)

            task.testcases = data.get('testcases', [])
            if not isinstance(task.testcases, list):
                api.abort(404)

            task.tester = data.get('tester', '')

            task.upload_dir = data.get('upload_dir', '')
            # print(task.to_json())
        task.test = test.id
        try:
            task.save()
        except ValidationError:
            api.abort(404)

        failed = []
        for endpoint in task.endpoint_list:
            ret = TaskQueue.push(task, endpoint, task.priority)
            if ret == None:
                failed.append(endpoint)
        if len(failed) != 0:
            return {'status': 404, 'data': task.to_json(), 'failed_endpoint': failed}

        return {'status': 0, 'data': task.to_json()}
