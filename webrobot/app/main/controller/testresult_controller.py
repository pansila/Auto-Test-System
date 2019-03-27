import os
import json
from pathlib import Path
from mongoengine import ValidationError

from flask import Flask, send_from_directory, render_template, url_for, make_response, request
from flask_restplus import Resource
from bson.objectid import ObjectId

from ..config import get_config
from ..util.dto import TestResultDto
from ..model.database import Task, Test, TestResult

api = TestResultDto.api

@api.route('/<path:path>')
@api.param('path', 'path of test result generated during the test')
class TestResultDownload(Resource):
    def get(self, path):
        path, filename = path.split('/')
        return send_from_directory(Path(os.getcwd()) / Path(get_config().TEST_RESULT_ROOT) / path, filename)

@api.route('/')
class TestResultRoot(Resource):
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
                ret.append(r)
        return make_response(render_template('test_result.html', tasks=ret), 200, headers)

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
