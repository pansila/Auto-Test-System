from flask import request
from flask_restplus import Resource

from ..util.dto import TaskQueueDto
from ..model.database import Test, Task, TaskQueue, QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX

api = TaskQueueDto.api

@api.route('/')
class TaskQueueController(Resource):
    @api.doc('get all task queues')
    def get(self):
        return [(task.endpoint_address, task.priority) for task in TaskQueue.objects({})]

    @api.response(201, 'Endpoint address successfully created.')
    @api.doc('create a task queue for the endpoint address')
    def post(self):
        data = request.json
        # print(data)
        endpoint_address = data['endpoint_address']
        try:
            TaskQueue.objects(endpoint_address=endpoint_address).get()
        except TaskQueue.MultipleObjectsReturned:
            print('task queue already exists')
            api.abort(404)
        except TaskQueue.DoesNotExist:
            pass

        for priority in (QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX):
            taskqueue = TaskQueue(endpoint_address=endpoint_address, priority=priority)
            taskqueue.save()
        return {'status': 0}