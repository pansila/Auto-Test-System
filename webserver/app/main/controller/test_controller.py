import aiofiles
import os, sys
import time
from async_files.utils import async_wraps
from bson import ObjectId
from pathlib import Path
from setuptools import sandbox
from contextlib import redirect_stdout
from io import StringIO

from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file, html
from sanic_openapi import doc

from ..util import async_copy, async_exists
from ..util.tempdir import TemporaryDirectory
from ..util.decorator import token_required, organization_team_required_by_args
from ..util.get_path import get_test_result_path, get_back_scripts_root, get_test_store_root
from task_runner.util.dbhelper import find_dependencies, find_pkg_dependencies, find_local_dependencies, generate_setup, query_package, repack_package
from ..config import get_config
from ..model.database import Task, Test, Package
from ..util.dto import TestDto, json_response
from ..util.tarball import make_tarfile_from_dir
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, EIO, EMFILE, EPERM

_test_cases = TestDto.test_cases
_test_suite_list = TestDto.test_suite_list

bp = Blueprint('test', url_prefix='/test')

@bp.get('/script')
@doc.summary('Get the test script')
@doc.description('Get the bundled file that contains all necessary test scripts that the test needs to run')
@doc.consumes(doc.String(name='id', description='The task id'))
@doc.consumes(doc.String(name='test', description='The test suite name'))
@doc.produces(201, doc.File())
@doc.produces(200, json_response)
# @token_required  #TODO
async def handler(request):
    task_id = request.args.get('id', None)
    if not task_id:
        return json(response_message(EINVAL, 'Field id is required'))

    test_script = request.args.get('test', None)

    task = await Task.find_one({'_id': ObjectId(task_id)})
    if not task:
        return json(response_message(ENOENT, 'Task not found'))
    organization = await task.organization.fetch()
    team = None
    if task.team:
        team = await task.team.fetch()

    result_dir = os.path.abspath(await get_test_result_path(task))
    scripts_root = await get_back_scripts_root(task)
    pypi_root = await get_test_store_root(task=task)
    package = None

    if sys.platform == 'win32':
        result_dir = '\\\\?\\' + result_dir

    test =  await task.test.fetch()
    package = await test.package.fetch()

    if not package:
        if not test_script:
            return response_message(SUCCESS), 204
        script_file = scripts_root / test_script
        if not await async_exists(script_file):
            return json(response_message(ENOENT, "file {} does not exist".format(script_file)))

        async with TemporaryDirectory(dir=result_dir) as tempDir:
            test_script_name = os.path.splitext(test_script)[0].split('/', 1)[0]
            deps = await find_local_dependencies(scripts_root, test_script, organization, team)
            await generate_setup(scripts_root, tempDir, deps, test_script_name, '0.0.1')
            with StringIO() as buf, redirect_stdout(buf):
                await async_wraps(sandbox.run_setup)(os.path.join(tempDir, 'setup.py'), ['bdist_egg'])
            deps = await find_dependencies(script_file, organization, team, 'Test Suite')
            dist = os.path.join(tempDir, 'dist')
            for pkg, version in deps:
                await async_copy(pypi_root / pkg.package_name / (await pkg.get_package_by_version(version).filename), dist)
            await make_tarfile_from_dir(os.path.join(result_dir, f'{test_script_name}.tar.gz'), dist)
            return await file(result_dir[4:] / f'{test_script_name}.tar.gz', status=201)
    else:
        async with TemporaryDirectory(dir=result_dir) as tempDir:
            dist = os.path.join(tempDir, 'dist')
            await aiofiles.os.mkdir(dist)
            deps = await find_pkg_dependencies(pypi_root, package, test.package_version, organization, team, 'Test Suite')
            for pkg, version in deps:
                if pkg.modified:
                    pack_file = await repack_package(pypi_root, scripts_root, pkg, version, tempDir)
                    await async_copy(pack_file, dist)
                else:
                    await async_copy(pypi_root / pkg.package_name / (await pkg.get_package_by_version(version)).filename, dist)
            await make_tarfile_from_dir(os.path.join(result_dir, 'all_in_one.tar.gz'), dist)
            return await file(os.path.join(result_dir[4:], 'all_in_one.tar.gz'), status=201)

@bp.get('/<test_suite>')
@doc.summary('Get the test cases of a test suite')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(doc.String(name='test_suite', description='The test suite to query'))
@doc.produces(_test_cases)
@token_required
@organization_team_required_by_args
async def handler(request, test_suite):
    organization = request.ctx.organization
    team = request.ctx.team

    test = await Test.find_one({'test_suite': test_suite, 'organization': organization.pk, 'team': team.pk if team else None})
    if not test:
        return json(response_message(ENOENT, 'Test {} not found'.format(test_suite)))

    return json(response_message(SUCCESS, test_cases=test.test_cases, test_suite=test.test_suite))

@bp.get('/detail')
@doc.summary('Get the test cases of a test suite')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(doc.String(name='id', description='The test suite id to query'), required=True)
@doc.produces(_test_cases)
@token_required
@organization_team_required_by_args
async def handler(request, test_suite):
    organization = request.ctx.organization
    team = request.ctx.team
    test_id = request.args.get('id', None)
    if not test_id:
        return json(response_message(EINVAL, 'field id is required'))

    test = await Test.find_one({'_id': ObjectId(test_id), 'organization': organization.pk, 'team': team.pk if team else None})
    if not test:
        return json(response_message(ENOENT, 'Test {} not found'.format(test_suite)))

    return json(response_message(SUCCESS, test_cases=test.test_cases, test_suite=test.test_suite))

class TestSuitesView(HTTPMethodView):
    @doc.summary('Get the test suite list which contains some necessary test details')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.produces(_test_suite_list)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        organization = request.ctx.organization
        team = request.ctx.team

        ret = []
        async for t in Test.find({'organization': organization.pk, 'team': team.pk if team else None}):
            if t.staled:
                continue
            author = await t.author.fetch()
            ret.append({
                'id': str(t.pk),
                'test_suite': t.test_suite,
                'path': t.path,
                'test_cases': t.test_cases,
                'variables': t.variables,
                'author': author.name
            })
        ret.sort(key=lambda x: x['path'])
        return json(response_message(SUCCESS, test_suites=ret))

bp.add_route(TestSuitesView.as_view(), '/')
