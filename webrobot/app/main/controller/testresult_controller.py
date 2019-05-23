import json
import os
from datetime import date, datetime, timedelta, timezone
from dateutil import parser
from pathlib import Path

from bson.objectid import ObjectId
from dateutil import tz
from flask import Flask, render_template, request, send_from_directory, url_for
from flask_restplus import Resource
from mongoengine import DoesNotExist, ValidationError

from ..config import get_config
from ..model.database import (QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Task, Test, TestResult)
from ..util.dto import TestResultDto
from ..util.errors import *

api = TestResultDto.api

@api.route('/<path:path>')
@api.param('path', 'path of test result generated during the test')
class TestResultDownload(Resource):
    def get(self, path):
        path, filename = path.split('/')
        return send_from_directory(Path(os.getcwd()) / Path(get_config().TEST_RESULT_ROOT) / path, filename)

@api.route('/view')
class TestResultView(Resource):
    def get(self):
        headers = {'Content-Type': 'text/html'}
        tasks = os.listdir(Path(get_config().TEST_RESULT_ROOT))
        ret = []
        for t in tasks:
            try:
                r = Task.objects(pk=t).get()
            except ValidationError:
                pass
            except Task.DoesNotExist:
                pass
            else:
                try:
                    r.test.test_suite
                except DoesNotExist:
                    continue
                ret.append(r)
        return make_response(render_template('test_result.html',
                                             tasks=ret,
                                             from_zone=tz.tzutc(),
                                             to_zone=tz.tzlocal()),
                             200, headers)

@api.route('/')
class TestResultRoot(Resource):
    def get(self):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        priority = request.args.get('priority', default=None)
        endpoint = request.args.get('endpoint', default=None)
        sort = request.args.get('sort', default='-run_date')
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        if start_date:
            start_date = parser.parse(start_date)
            if end_date is None:
                end_date = datetime.now(timezone.utc)
            else:
                end_date = parser.parse(end_date)

            if (start_date - end_date).days > 0:
                return error_message(EINVAL, 'start date {} is larger than end date {}'.format(start_date, end_date)), 401

            query = {'run_date__lte': end_date, 'run_date__gte': start_date}
        else:
            query = {}

        page = int(page)
        limit = int(limit)

        if priority and priority != '' and priority.isdigit() and \
                int(priority) >= QUEUE_PRIORITY_MIN and int(priority) <= QUEUE_PRIORITY_MAX:
            query['priority'] = priority

        if title and priority != '':
            query['test_suite__contains'] = title

        if endpoint and endpoint != '':
            query['endpoint_run'] = endpoint

        dirs = os.listdir(Path(get_config().TEST_RESULT_ROOT))
        all_tasks = Task.objects(id__in=dirs, **query).order_by(sort)
        tasks = all_tasks[(page - 1) * limit : page * limit]
        tasks = [t.to_json() for t in tasks]

        return {'items': tasks, 'total': all_tasks.count()}

@api.route('/')
class TestResultCreate(Resource):
    @api.doc('create the test result for the task in the database')
    def post(self):
        data = request.json
        if data is None:
            return error_message(EINVAL, "payload of the request is empty"), 400

        task_id = data.get('task_id', None)
        if task_id == None:
            return error_message(EINVAL, "field task_id is required"), 400
        try:
            task = Task.objects(pk=task_id).get()
        except Task.DoesNotExist as e:
            print(e)
            return error_message(ENOENT, "task not found"), 404

        test_case = data.get('test_case', None)
        if test_case == None:
            return error_message(EINVAL, "field test_case is required"), 400

        test_result = TestResult()
        test_result.test_case = test_case
        test_result.task = ObjectId(task_id)
        try:
            test_result.save()
        except ValidationError as e:
            print(e)
            return error_message(EPERM, "test result validation failed"), 400

        task.test_results.append(test_result)
        task.save()

@api.route('/<task_id>')
@api.param('task_id', 'id of the task for which to upload the results')
class TestResultUpload(Resource):
    @api.doc('update the test results')
    def post(self, task_id):
        data = request.json
        if data is None:
            return
        if isinstance(data, str):
            data = json.loads(data)

        try:
            task = Task.objects(pk=task_id).get()
        except Task.DoesNotExist as e:
            print(e)
            return error_message(ENOENT, "task not found"), 404

        if task.test_results is None or len(task.test_results) == 0:
            return error_message(ENOENT, "test result not found"), 404

        cur_test_result = task.test_results[-1]

        for k, v in data.items():
            if k != 'more_result' and getattr(TestResult, k, None) != None:
                setattr(cur_test_result, k, v)
            else:
                cur_test_result.more_result[k] = v
        try:
            cur_test_result.save()
        except ValidationError as e:
            print(e)
            return error_message(EPERM, "test result validation failed"), 400
