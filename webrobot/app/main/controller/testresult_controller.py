import os
from pathlib import Path
from mongoengine import ValidationError

from flask import Flask, send_from_directory, render_template, url_for, make_response
from flask_restplus import Resource

from ..config import get_config
from ..util.dto import TestResultDto
from ..model.database import Task, Test

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