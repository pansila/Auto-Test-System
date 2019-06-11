import os
from pathlib import Path
import datetime
from datetime import date, datetime, timedelta

from flask import request, Response, send_from_directory
from flask_restplus import Resource
from mongoengine import ValidationError

from app.main.util.decorator import token_required
from app.main.util.request_parse import parse_organization_team, get_test_result_root
from ..util.tarball import path_to_dict
from ..model.database import *
from ..util.dto import TaskDto
from ..config import get_config
from ..util.errors import *

api = TaskDto.api

@api.route('/detail/<task_id>')
class TaskStatistics(Resource):
    @token_required
    @api.doc('get the detailed result for a task')
    def get(self, task_id, user):
        task = Task.objects(id=task_id).first()
        if not task:
            return error_message(ENOENT, 'Task not found'), 404

        result_dir = get_test_result_root(task)
        if not os.path.exists(result_dir):
            return error_message(ENOENT, 'Task result directory not found'), 404

        with open(result_dir / 'output.xml', encoding='utf-8') as f:
            return Response(f.read(), mimetype='text/xml')

@api.route('/result_files')
class ScriptManagement(Resource):
    @token_required
    def get(self, user):
        task_id = request.args.get('task_id', default=None)
        if not task_id:
            return error_message(EINVAL, 'Field task_id is required'), 400

        task = Task.objects(id=task_id).first()
        if not task:
            return error_message(ENOENT, 'Task not found'), 404

        ret = parse_organization_team(user, request.args)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret

        if task.organization != organization or task.team != team:
            return error_message(EPERM, 'Accessing resources that not belong to you is not allowed'), 403

        result_dir = get_test_result_root(task)
        result_files = path_to_dict(result_dir)

        return error_message(SUCCESS, files=result_files)

@api.route('/result_file')
class ScriptManagement(Resource):
    @token_required
    def get(self, user):
        file_path = request.args.get('file', default=None)
        if not file_path:
            return error_message(EINVAL, 'Field file is required'), 400

        task_id = request.args.get('task_id', default=None)
        if not task_id:
            return error_message(EINVAL, 'Field task_id is required'), 400

        task = Task.objects(id=task_id).first()
        if not task:
            return error_message(ENOENT, 'Task not found'), 404

        ret = parse_organization_team(user, request.args)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret

        if task.organization != organization or task.team != team:
            return error_message(EPERM, 'Accessing resources that not belong to you is not allowed'), 403

        result_dir = get_test_result_root(task)
        return send_from_directory(Path(os.getcwd()) / result_dir, file_path)

@api.route('/')
class TaskController(Resource):
    @token_required
    @api.doc('get the task statistics')
    def get(self, user):
        start_date = request.args.get('start_date', default=(datetime.datetime.utcnow().timestamp()-86300)*1000)
        end_date = request.args.get('end_date', default=(datetime.datetime.utcnow().timestamp() * 1000))

        start_date = datetime.datetime.fromtimestamp(int(start_date)/1000)
        end_date = datetime.datetime.fromtimestamp(int(end_date)/1000)

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

    @token_required
    @api.response(201, 'Test suite successfully ran.')
    @api.doc('run a test suite')
    def post(self, user):
        data = request.json
        if data is None:
            return error_message(EINVAL, 'The request data is empty'), 400

        task = Task()
        test_suite = data.get('test_suite', None)
        if test_suite == None:
            return error_message(EINVAL, 'Field test_suite is required'), 400

        task.test_suite = test_suite

        ret = parse_organization_team(user, request.json)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret

        query = {'test_suite': task.test_suite, 'organization': organization}
        if team:
            query['team'] = team
        test = Test.objects(**query).first()
        if not test:
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

        task.tester = owner
        task.upload_dir = data.get('upload_dir', '')
        task.test = test
        task.organization = organization
        task.team = team
        try:
            task.save()
        except ValidationError:
            return error_message(EINVAL, 'Task validation failed'), 400

        failed = []
        for endpoint in task.endpoint_list:
            if task.parallelization:
                new_task = Task()
                for name in task:
                    if name != 'id' and not name.startswith('_') and not callable(task[name]):
                        new_task[name] = task[name]
                else:
                    new_task.save()
                    ret = TaskQueue.find(endpoint_address=endpoint, priority=task.priority, organization=organization, team=team)
                    if not ret:
                        failed.append(endpoint)
                    else:
                        taskqueue, _ = ret
                        ret = taskqueue.first().push(new_task)
                        if ret == None:
                            failed.append(endpoint)
            else:
                ret = TaskQueue.find(endpoint_address=endpoint, priority=task.priority, organization=organization, team=team)
                if not ret:
                    failed.append(endpoint)
                else:
                    taskqueue, _ = ret
                    ret = taskqueue.first().push(task)
                    if ret == None:
                        failed.append(endpoint)
        else:
            if task.parallelization:
                task.delete()
        if len(failed) != 0:
            return error_message(UNKNOWN_ERROR, 'Task scheduling failed'), 401

    @token_required
    @api.doc('update a task')
    def patch(self, user):
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

    @token_required
    @api.doc('cancel a task')
    def delete(self, user):
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

        task = Task.objects(pk=task_id).first()
        if not task:
            return error_message(ENOENT, 'Task not found'), 404

        event = Event()
        event.code = EVENT_CODE_CANCEL_TASK
        event.message['address'] = address
        event.message['priority'] = priority
        event.message['task_id'] = task_id
        event.save()

        ret = EventQueue.find(organization=task.test.organization, team=task.test.team)
        if not ret:
            return error_message(ENOENT, 'Event queue not found'), 404

        eventqueue, _ = ret
        if not eventqueue.push(event):
            return error_message(EPERM, 'Pushing the event to event queue failed'), 403
