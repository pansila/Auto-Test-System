import os
import shutil
import tempfile
import time
from pathlib import Path
from setuptools import sandbox
from contextlib import redirect_stdout
from io import StringIO

from flask import send_from_directory, request, current_app
from flask_restx import Resource

from ..util.decorator import token_required, organization_team_required_by_args
from ..util.get_path import get_test_result_path, get_back_scripts_root, get_test_store_root
from task_runner.util.dbhelper import find_dependencies, find_pkg_dependencies, find_local_dependencies, generate_setup, query_package
from ..config import get_config
from ..model.database import Task, Test, Package
from ..util.dto import TestDto
from ..util.tarball import pack_files, make_tarfile, make_tarfile_from_dir
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, EIO, EMFILE

api = TestDto.api
_test_cases = TestDto.test_cases
_test_suite = TestDto.test_suite


@api.route('/script')
@api.response(404, 'Script not found.')
@api.response(200, 'Download the script successfully.')
class ScriptDownload(Resource):
    # @token_required
    @api.doc('get_test_script')
    @api.param('id', description='The task id')
    @api.param('test', description='The test suite name')
    def get(self):
        """
        Get the test script

        Get the bundled file that contains all necessary test scripts that the test needs to run
        """
        task_id = request.args.get('id', None)
        if not task_id:
            return response_message(EINVAL, 'Field id is required'), 400

        test_script = request.args.get('test', None)
        if not test_script:
            return response_message(EINVAL, 'Field test is required'), 400

        task = Task.objects(pk=task_id).first()
        if not task:
            return response_message(ENOENT, 'Task not found'), 404

        test_path = None if '/' not in test_script else test_script.split('/', 1)[0]

        result_dir = get_test_result_path(task)
        scripts_root = get_back_scripts_root(task)
        pypi_root = get_test_store_root(task=task)
        package = None

        script_file = scripts_root / test_script
        if not os.path.exists(script_file):
            return response_message(ENOENT, "file {} does not exist".format(script_file)), 404

        if task.test.package and test_path in task.test.package.py_packages:
            package = task.test.package
        elif test_path:
            package = query_package(test_path, task.organization, task.team, 'Test Suite')

        if not package:
            with tempfile.TemporaryDirectory(dir=result_dir) as tempDir:
                test_script_name = os.path.splitext(test_script)[0].split('/', 1)[0]
                deps = find_local_dependencies(scripts_root, test_script, task.organization, task.team)
                generate_setup(scripts_root, tempDir, deps, test_script_name, '0.0.1')
                with StringIO() as buf, redirect_stdout(buf):
                    sandbox.run_setup(os.path.join(tempDir, 'setup.py'), ['bdist_egg'])
                deps = find_dependencies(script_file, task.organization, task.team, 'Test Suite')
                dist = os.path.join(tempDir, 'dist')
                for pkg, version in deps:
                    shutil.copy(pypi_root / pkg.package_name / pkg.get_package_by_version(version), dist)
                make_tarfile_from_dir(os.path.join(result_dir, f'{test_script_name}.tar.gz'), dist)
                return send_from_directory(Path(os.getcwd()) / result_dir, f'{test_script_name}.tar.gz')
        else:
            with tempfile.TemporaryDirectory(dir=result_dir) as tempDir:
                dist = os.path.join(tempDir, 'dist')
                os.mkdir(dist)
                deps = find_pkg_dependencies(pypi_root, package, task.test.package_version, task.organization, task.team, 'Test Suite')
                for pkg, version in deps:
                    shutil.copy(pypi_root / pkg.package_name / pkg.get_package_by_version(version), dist)
                make_tarfile_from_dir(os.path.join(result_dir, f'{os.path.basename(test_script)}.tar.gz'), dist)
                return send_from_directory(Path(os.getcwd()) / result_dir, f'{os.path.basename(test_script)}.tar.gz')

@api.route('/<test_suite>')
@api.param('test_suite', 'The test suite to query')
@api.response(404, 'Script not found.')
class TestSuiteGet(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get_the_test_cases')
    @api.marshal_with(_test_cases)
    def get(self, test_suite, **kwargs):
        """Get the test cases of a test suite"""
        organization = kwargs['organization']
        team = kwargs['team']

        test = Test.objects(test_suite=test_suite, organization=organization, team=team).first()
        if not test:
            return response_message(ENOENT, 'Test {} not found'.format(test_suite)), 404

        return {
            'test_cases': test.test_cases,
            'test_suite': test.test_suite
        }

@api.route('/')
class TestSuitesList(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get_the_test_suite_list')
    @api.marshal_list_with(_test_suite)
    def get(self, **kwargs):
        """Get the test suite list which contains some necessary test details"""
        organization = kwargs['organization']
        team = kwargs['team']
        
        tests = Test.objects(organization=organization, team=team)

        ret = []
        for t in tests:
            if t.staled:
                continue
            ret.append({
                'id': str(t.id),
                'test_suite': t.test_suite,
                'path': t.path,
                'test_cases': t.test_cases,
                'variables': t.variables,
                'author': t.author.name
            })
        ret.sort(key=lambda x: x['path'])
        return ret
