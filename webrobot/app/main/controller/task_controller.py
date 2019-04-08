import os
from pathlib import Path
from datetime import date, datetime, timedelta

from flask import request
from flask_restplus import Resource
from mongoengine import ValidationError

from ..model.database import (QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Task, TaskQueue, Test)
from ..util.dto import TaskDto
from ..config import get_config

api = TaskDto.api

@api.route('/')
class TaskStatistics(Resource):
    @api.doc('get the statistics for a task')
    def get(self):
        start_date = request.args.get('start_date', default=(datetime.utcnow().timestamp()-86300)*1000)
        end_date = request.args.get('end_date', default=(datetime.utcnow().timestamp() * 1000))

        start_date = datetime.fromtimestamp(int(start_date)/1000)
        end_date = datetime.fromtimestamp(int(end_date)/1000)

        if (start_date - end_date).seconds > 0:
            print(start_date - end_date)
            api.abort(404)

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

@api.route('/')
class TaskController(Resource):
    @api.response(201, 'Test suite successfully ran.')
    @api.doc('run a test suite')
    def post(self):
        data = request.json
        if data is None:
            print('The request data is empty')
            api.abort(404)

        task = Task()
        test_suite = data.get('test_suite', None)
        if test_suite == None:
            print('Field test_suite should be filled')
            api.abort(404)
        task.test_suite = test_suite

        try:
            test = Test.objects(test_suite=task.test_suite).get()
        except Test.DoesNotExist:
            print('The requested test suite is not found')
            api.abort(404)

        endpoint_list = data.get('endpoint_list', None)
        if endpoint_list == None:
            print('endpoint list is not included in the request')
            api.abort(404)
        if not isinstance(endpoint_list, list):
            print('endpoint list is not a list')
            api.abort(404)
        if len(endpoint_list) == 0:
            print('endpoint list is empty')
            api.abort(404)
        task.endpoint_list = endpoint_list

        priority = data.get('priority', QUEUE_PRIORITY_DEFAULT)
        if priority < QUEUE_PRIORITY_MIN or priority > QUEUE_PRIORITY_MAX:
            print('task priority is out of range')
            api.abort(404)
        task.priority = priority

        parallelization = data.get('parallelization', False)
        task.parallelization = parallelization == True

        variables = data.get('variables', {})
        if not isinstance(variables, dict):
            print('variables should be a dictionary')
            api.abort(404)
        task.variables = variables

        testcases = data.get('testcases', [])
        if not isinstance(testcases, list):
            print('testcases should be a list')
            api.abort(404)
        task.testcases = testcases

        tester = data.get('tester', None)
        if tester == None:
            print('Field tester should not be empty')
            api.abort(404)
        task.tester = tester

        task.upload_dir = data.get('upload_dir', '')
        task.test = test.id
        try:
            task.save()
        except ValidationError:
            print('Task validation failed')
            api.abort(404)

        failed = []
        for endpoint in task.endpoint_list:
            ret = TaskQueue.push(task, endpoint, task.priority)
            if ret == None:
                failed.append(endpoint)
        if len(failed) != 0:
            print('Task scheduling failed')
            api.abort(404)

        return {'status': 0, 'data': task.to_json()}
