import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_restplus import Resource

from ..config import get_config
from ..model.database import Test
from ..util.dto import TestDto
from ..util.tarball import make_tarfile, pack_files

api = TestDto.api

TARBALL_TEMP = Path('temp')
SCRIPT_ROOT = Path(get_config().SCRIPT_ROOT)

@api.route('/script/<test_suite>')
@api.param('test_suite', 'the test suite to download the script')
@api.response(404, 'Script not found.')
class ScriptDownload(Resource):
    def get(self, test_suite):
        if test_suite.endswith('.py'):
            test_suite = test_suite[0:-3]

        script_file = SCRIPT_ROOT / (test_suite + '.py')
        if not os.path.exists(script_file):
            print("file {} does not exist".format(script_file))
            return None

        tarball = pack_files(test_suite, SCRIPT_ROOT, TARBALL_TEMP)
        if not tarball:
            api.abort(404)
        else:
            tarball = os.path.basename(tarball)
            return send_from_directory(Path(os.getcwd()) / TARBALL_TEMP, tarball)

@api.route('/<test_suite>')
@api.param('test_suite', 'the test suite to query')
@api.response(404, 'Script not found.')
class TestSuiteGet(Resource):
    def get(self, test_suite):
        try:
            test = Test.objects(test_suite=test_suite).get()
        except Test.DoesNotExist:
            print('Test not found')
            api.abort(404)

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
