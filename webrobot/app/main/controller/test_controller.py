import os
import time
from pathlib import Path

from flask import Flask, send_from_directory
from flask_restplus import Resource

from ..config import get_config
from ..model.database import Test
from ..util.dto import TestDto
from ..util.tarball import make_tarfile, pack_files
from ..util.errors import *

api = TestDto.api

TARBALL_TEMP = Path('temp')
BACKING_SCRIPT_ROOT = Path(get_config().BACKING_SCRIPT_ROOT)
try:
    os.mkdir(TARBALL_TEMP)
except FileExistsError:
    pass


@api.route('/script/<test_suite>')
@api.param('test_suite', 'the test suite to download the script')
@api.response(404, 'Script not found.')
class ScriptDownload(Resource):
    def get(self, test_suite):
        if test_suite.endswith('.py'):
            test_suite = test_suite[0:-3]

        script_file = BACKING_SCRIPT_ROOT / (test_suite + '.py')
        if not os.path.exists(script_file):
            return error_message(ENOENT, "file {} does not exist".format(script_file)), 404

        for _ in range(3):
            tarball = pack_files(test_suite, BACKING_SCRIPT_ROOT, TARBALL_TEMP)
            if tarball is None:
                print("retry packaging files")
                time.sleep(1)
            else:
                tarball = os.path.basename(tarball)
                return send_from_directory(Path(os.getcwd()) / TARBALL_TEMP, tarball)
        else:
            return error_message(EIO, "packaging files failed"), 404

@api.route('/<test_suite>')
@api.param('test_suite', 'the test suite to query')
@api.response(404, 'Script not found.')
class TestSuiteGet(Resource):
    def get(self, test_suite):
        try:
            test = Test.objects(test_suite=test_suite).get()
        except Test.DoesNotExist as e:
            print(e)
            return error_message(ENOENT, 'Test {} not found'.format(test_suite)), 404

        return test.to_json()

@api.route('/')
class TestSuitesList(Resource):
    def get(self):
        tests = Test.objects({})
        ret = []
        for t in tests:
            ret.append({
                'test_suite': t.test_suite,
                'test_cases': t.test_cases,
                'variables': t.variables,
                'author': t.author
            })
        return ret
