import json
import os
from pathlib import Path

from bson.objectid import ObjectId
from dateutil import tz
from flask import Flask, render_template, request, send_from_directory, url_for
from flask_restplus import Resource
from mongoengine import DoesNotExist, ValidationError

from ..config import get_config
from ..model.database import Task, Test, TestResult
from ..util.dto import TestResultDto

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
        sort = request.args.get('sort', default='run_date')

        page = int(page)
        limit = int(limit)

        dirs = os.listdir(Path(get_config().TEST_RESULT_ROOT))
        all_tasks = Task.objects(id__in=dirs).order_by(sort)
        tasks = all_tasks[(page - 1) * limit : page * limit]
        tasks = [t.to_json() for t in tasks]

        return {'items': tasks, 'total': len(all_tasks)}

@api.route('/')
class TestResultCreate(Resource):
    @api.doc('create the test result for the task in the database')
    def post(self):
        data = request.json
        if data is None:
            api.abort(404)

        task_id = data.get('task_id', None)
        if task_id == None:
            api.abort(404)
        try:
            task = Task.objects(pk=task_id).get()
        except Task.DoesNotExist:
            api.abort(404)

        test_case = data.get('test_case', None)
        if test_case == None:
            api.abort(404)

        test_result = TestResult()
        test_result.test_case = test_case
        test_result.task = ObjectId(task_id)
        test_result.save()

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
        except Task.DoesNotExist:
            api.abort(404)

        if task.test_results is None or len(task.test_results) == 0:
            api.abort(404)

        cur_test_result = task.test_results[-1]

        for k, v in data.items():
            if k != 'more_result' and getattr(TestResult, k, None) != None:
                setattr(cur_test_result, k, v)
            else:
                cur_test_result.more_result[k] = v
        try:
            cur_test_result.save()
        except ValidationError:
            api.abort(404)
