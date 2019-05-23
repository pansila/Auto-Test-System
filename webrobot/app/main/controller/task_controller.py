import os
from pathlib import Path
from datetime import date, datetime, timedelta

from flask import request, Response
from flask_restplus import Resource
from mongoengine import ValidationError

from ..model.database import (EVENT_CODE_CANCEL_TASK, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Task, TaskQueue, Test, Event, EventQueue)
from ..util.dto import TaskDto
from ..config import get_config
from ..util.errors import *

api = TaskDto.api

@api.route('/result/<task_id>')
class TaskStatistics(Resource):
    @api.doc('get the detailed result for a task')
    def get(self, task_id):
        dirs = os.listdir(Path(get_config().TEST_RESULT_ROOT))
        if task_id not in dirs:
            return error_message(ENOENT, 'Task result directory not found'), 404

        try:
            task = Task.objects(id=task_id).get()
        except Task.DoesNotExist as e:
            print(e)
            return error_message(ENOENT, 'Task not found'), 404

        with open(Path(get_config().TEST_RESULT_ROOT) / task_id / 'output.xml', encoding='utf-8') as f:
            return Response(f.read(), mimetype='text/xml')

@api.route('/')
class TaskController(Resource):
    @api.doc('get the statistics for a task')
    def get(self):
        start_date = request.args.get('start_date', default=(datetime.utcnow().timestamp()-86300)*1000)
        end_date = request.args.get('end_date', default=(datetime.utcnow().timestamp() * 1000))

        start_date = datetime.fromtimestamp(int(start_date)/1000)
        end_date = datetime.fromtimestamp(int(end_date)/1000)

        if (start_date - end_date).days > 0:
            return error_message(EINVAL, 'start date {} is larger than end date {}'.format(start_date, end_date)), 401

        delta = end_date - start_date
        days = delta.days
        if delta % timedelta(days=1):
            days = days + 1

        stats = []
        start = start_date
        end = start + timedelta(days=1) 

        for d in range(days):
            if d == (days - 1):
                end = end_date

            tasks = Task.objects(status='successful', run_date__lte=end, run_date__gte=start)
            succeeded = len(tasks)

            tasks = Task.objects(status='failed', run_date__lte=end, run_date__gte=start)
            failed = len(tasks)

            tasks = Task.objects(status='running', run_date__lte=end, run_date__gte=start)
            running = len(tasks)

            tasks = Task.objects(status='waiting', schedule_date__lte=end, schedule_date__gte=start)
            waiting = len(tasks)
            
            stats.append({
                'succeeded': succeeded,
                'failed': failed,
                'running': running,
                'waiting': waiting,
            })

            start = start + timedelta(days=1)
            end = start + timedelta(days=1)
        return stats

    @api.response(201, 'Test suite successfully ran.')
    @api.doc('run a test suite')
    def post(self):
        data = request.json
        if data is None:
            return error_message(EINVAL, 'The request data is empty'), 400

        task = Task()
        test_suite = data.get('test_suite', None)
        if test_suite == None:
            return error_message(EINVAL, 'Field test_suite is required'), 400
        task.test_suite = test_suite

        try:
            test = Test.objects(test_suite=task.test_suite).get()
        except Test.DoesNotExist:
            return error_message(ENOENT, 'The requested test suite is not found'), 404

        endpoint_list = data.get('endpoint_list', None)
        if endpoint_list == None:
            return error_message(EINVAL, 'Endpoint list is not included in the request'), 400
        if not isinstance(endpoint_list, list):
            return error_message(EINVAL, 'Endpoint list is not a list'), 400
        if len(endpoint_list) == 0:
            return error_message(EINVAL, 'Endpoint list is empty'), 400
        task.endpoint_list = endpoint_list

        priority = int(data.get('priority', QUEUE_PRIORITY_DEFAULT))
        if priority < QUEUE_PRIORITY_MIN or priority > QUEUE_PRIORITY_MAX:
            return error_message(ERANGE, 'Task priority is out of range'), 400
        task.priority = priority

        parallelization = data.get('parallelization', False)
        task.parallelization = parallelization == True

        variables = data.get('variables', {})
        if not isinstance(variables, dict):
            return error_message(EINVAL, 'Variables should be a dictionary'), 400
        task.variables = variables

        testcases = data.get('testcases', [])
        if not isinstance(testcases, list):
            return error_message(EINVAL, 'Testcases should be a list'), 400
        task.testcases = testcases

        tester = data.get('tester', None)
        if tester == None:
            return error_message(EINVAL, 'Field tester should not be empty'), 400
        task.tester = tester

        task.upload_dir = data.get('upload_dir', '')
        task.test = test.id
        try:
            task.save()
        except ValidationError:
            return error_message(EPERM, 'Task validation failed'), 400

        failed = []
        for endpoint in task.endpoint_list:
            if task.parallelization:
                new_task = Task()
                for name in task:
                    if name != 'id' and not name.startswith('_') and not callable(task[name]):
                        new_task[name] = task[name]
                else:
                    new_task.save()
                    ret = TaskQueue.push(new_task, endpoint, task.priority)
                    if ret == None:
                        failed.append(endpoint)
            else:
                ret = TaskQueue.push(task, endpoint, task.priority)
                if ret == None:
                    failed.append(endpoint)
        else:
            if task.parallelization:
                task.delete()
        if len(failed) != 0:
            return error_message(EPERM, 'Task scheduling failed'), 403

        return {'status': 0, 'data': task.to_json()}

    @api.doc('update a task')
    def patch(self):
        data = request.json
        if data is None:
            return error_message(EINVAL, 'The request data is empty'), 400

        task_id = data.get('_id', None)
        task_id = task_id['$oid']
        if task_id == None:
            return error_message(EINVAL, 'Field _id is required'), 400

        comment = data.get('comment', None)
        if comment == None:
            return error_message(EINVAL, 'Field comment is required'), 400

        try:
            task = Task.objects(id=task_id).get()
        except Task.DoesNotExist:
            return error_message(ENOENT, 'The requested task is not found'), 404
        else:
            task.comment = comment
            task.save()

    @api.doc('cancel a task')
    def delete(self):
        data = request.json
        if data is None:
            print('The request data is empty')
            api.abort(404)
            return error_message(EINVAL, 'The request data is empty'), 400

        task_id = data.get('task_id', None)
        if task_id is None:
            return error_message(EINVAL, 'Field task_id is required'), 400
        address = data.get('address', None)
        if address is None:
            return error_message(EINVAL, 'Field address is required'), 400
        priority = data.get('priority', None)
        if priority is None:
            return error_message(EINVAL, 'Field priority is required'), 400
        status = data.get('status', None)
        if status is None:
            return error_message(EINVAL, 'Field status is required'), 400

        event = Event()
        event.code = EVENT_CODE_CANCEL_TASK
        event.message['address'] = address
        event.message['priority'] = priority
        event.message['task_id'] = task_id
        event.save()

        if EventQueue.push(event) is None:
            return error_message(EPERM, 'Pushing the event to event queue failed'), 403
