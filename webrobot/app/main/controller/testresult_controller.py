import os
from pathlib import Path

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
        return send_from_directory(Path(os.getcwd()) / 'static/results/' / path, filename)

@api.route('/')
class TestResultRoot(Resource):
    def get(self):
        headers = {'Content-Type': 'text/html'}
        tasks = os.listdir('static/results')
        try:
            tasks = [Task.objects(pk=t).get() for t in tasks]
        except Task.DoesNotExist:
            api.abort(404)
        return make_response(render_template('test_result.html', tasks=tasks), 200, headers)