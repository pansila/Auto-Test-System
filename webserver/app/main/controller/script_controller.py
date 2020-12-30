import aiofiles
import os
import re
from pathlib import Path

from async_files.utils import async_wraps
from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file
from sanic_openapi import doc

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form
from app.main.util.get_path import get_user_scripts_root, get_back_scripts_root, is_path_secure
from task_runner.util.dbhelper import db_update_test
from ..model.database import Test, Package
from ..util import async_rmtree, async_exists, async_makedirs, async_isfile
from ..util.dto import ScriptDto, json_response
from ..util.tarball import path_to_dict
from ..util.response import response_message, EINVAL, ENOENT, UNKNOWN_ERROR, SUCCESS, EIO

_script_file_list = ScriptDto.script_file_list
_update_script = ScriptDto.update_script
_script_query = ScriptDto.script_query
_upload_scripts = ScriptDto.upload_scripts


bp = Blueprint('script', url_prefix='/script')

class ScriptView(HTTPMethodView):
    @doc.summary('A compound method to return either the script file list or the script file content')
    @doc.description('When field file is None, return the file list as per script_type, otherwise return the specified file.')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_script_query)
    @doc.produces(200, _script_file_list)
    @doc.produces(201, doc.File())
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        script_path = request.args.get('file', default=None)
        script_type = request.args.get('script_type', default=None)

        organization = request.ctx.organization
        team = request.ctx.team

        test_libraries_root = await get_back_scripts_root(team=team, organization=organization)
        test_scripts_root = await get_user_scripts_root(team=team, organization=organization)

        if script_path:
            if script_type is None:
                return json(response_message(EINVAL, 'Field script_type is required'))
            if script_type == 'test_scripts':
                return await file(test_scripts_root / script_path, status=201)
            elif script_type == 'test_libraries':
                return await file(test_libraries_root / script_path, status=201)
            else:
                return json(response_message(EINVAL, 'Unsupported script type ' + script_type))
        elif script_type:
            return json(response_message(EINVAL, 'Field file is required'))

        test_scripts = await async_wraps(path_to_dict)(test_scripts_root)
        test_libraries = await async_wraps(path_to_dict)(test_libraries_root)
        return json(response_message(SUCCESS, test_scripts=test_scripts, test_libraries=test_libraries))

    @doc.summary('update the script file content')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_update_script, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def post(self, request):
        script = request.json.get('file', None)
        if not script:
            return json(response_message(EINVAL, 'Field file is required'))
        if not is_path_secure(script):
            return json(response_message(EINVAL, 'Illegal file path'))

        new_name = request.json.get('new_name', None)
        if new_name:
            if not is_path_secure(new_name):
                return json(response_message(EINVAL, 'Illegal new name'))

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return json(response_message(EINVAL, 'Field script_type is required'))

        content = request.json.get('content', None)
        if content is None and new_name is None:
            return json(response_message(EINVAL, 'Field content is required'))

        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user
        package = None
        
        if script_type == 'test_scripts':
            root = await get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'test_libraries':
            root = await get_back_scripts_root(team=team, organization=organization)
        else:
            return json(response_message(EINVAL, 'Unsupported script type ' + script_type))

        dirname = os.path.dirname(script).split('/')[0]
        basename = os.path.basename(script)

        if script_type == 'test_scripts' and basename.endswith('.md'):
            test = await Test.find_one({'test_suite': os.path.splitext(basename)[0], 'path': dirname})
            if not test:
                return json(response_message(ENOENT, 'test suite not found'))
        elif script_type == 'test_libraries' and dirname:
            package = await Package.find_one({'py_packages': dirname})
            if not package:
                return json(response_message(ENOENT, 'package not found'))

        if not await async_exists(root / dirname):
            await async_makedirs(root / dirname)

        if content or content == '':
            if script_type == 'test_scripts':
                content = re.sub(r'\\([{}*_\.])', r'\1', content)
            elif script_type == 'test_libraries':
                content = re.sub(r'\r\n', '\n', content)

            if basename:
                async with aiofiles.open(root / script, 'w', encoding='utf-8') as f:
                    await f.write(content)

        if new_name:
            if basename:
                new_path = os.path.join(dirname, new_name)
                await aiofiles.os.rename(root / script, root / new_path)
                if script_type == 'test_scripts' and test: # not md files
                    test.test_suite = os.path.splitext(new_name)[0]
                    await test.commit()
            else:
                await aiofiles.os.rename(root / script, root / os.path.dirname(dirname) / new_name)

        if basename and script_type == 'test_scripts':
            _script = str(Path(dirname) / new_name) if new_name else script
            if _script.endswith('.md'):
                ret = await db_update_test(root, _script, user, organization, team)
                if not ret:
                    return json(response_message(UNKNOWN_ERROR, 'Failed to update test suite'))

        if script_type == 'test_libraries' and package:
            package.modified = True
            await package.commit()

        return json(response_message(SUCCESS))

    @doc.summary('delete the script file')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_script_query, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        
        script = request.json.get('file', None)
        if not script:
            return json(response_message(EINVAL, 'Field file is required'))
        if not is_path_secure(script):
            return json(response_message(EINVAL, 'Referencing to Upper level directory is not allowed'))

        dirname = os.path.dirname(script)
        basename = os.path.basename(script)

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return json(response_message(EINVAL, 'Field script_type is required'))

        if script_type == 'test_scripts':
            root = await get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'test_libraries':
            root = await get_back_scripts_root(team=team, organization=organization)
        else:
            return json(response_message(EINVAL, 'Unsupported script type ' + script_type))

        if not await async_exists(root / script):
            return json(response_message(ENOENT, 'File/directory doesn\'t exist'))

        if await async_isfile(root / script):
            try:
                await aiofiles.os.remove(root / script)
            except OSError as err:
                logger.exception(err)
                return json(response_message(EIO, 'Error happened while deleting the file'))

            if script_type == 'test_scripts':
                cnt = 0
                async for test in Test.find({'test_suite': os.path.splitext(basename)[0], 'path': dirname, 'organization': organization.pk, 'team': team.pk if team else None}):
                    await test.delete()
                    cnt += 1
                if cnt == 0:
                    return json(response_message(ENOENT, 'Test suite not found in the database'))
        else:
            if script_type == 'test_scripts':
                cnt = 0
                async for test in Test.find({'organization': organization.pk, 'team': team.pk if team else None}):
                    if test.path.startswith(dirname):
                        await test.delete()
                        cnt += 1
                if cnt == 0:
                    logger.error(f'Test suite not found in the database under the path {dirname}')
            try:
                await async_rmtree(root / script)
            except OSError as err:
                logger.exception(err)
                return json(response_message(EIO, 'Error happened while deleting the directory'))

        return json(response_message(SUCCESS))

@bp.post('/upload')
@doc.summary('upload the scripts')
@doc.description('''\
    Note: Files in the form request payload are tuples of file name and file content
    which can't be explicitly listed here. Please check out the form data format on the web.
    Usually browser will take care of it.
''')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_upload_scripts, location="formData", content_type="multipart/form-data")
@doc.produces(json_response)
@token_required
@organization_team_required_by_form
async def handler(request):
    found = False

    organization = request.ctx.organization
    team = request.ctx.team
    user = request.ctx.user
    
    script_type = request.form.get('script_type', None)
    if script_type is None:
        return json(response_message(EINVAL, 'Field script_type is required'))

    if script_type == 'test_scripts':
        root = await get_user_scripts_root(team=team, organization=organization)
    elif script_type == 'test_libraries':
        root = await get_back_scripts_root(team=team, organization=organization)
    else:
        return json(response_message(EINVAL, 'Unsupported script type ' + script_type))

    if not await async_exists(root):
        await aiofiles.os.mkdir(root)

    for name, file in request.files.items():
        if not is_path_secure(file.name):
            return json(response_message(EINVAL, 'saving file with an illegal file name'))
        found = True
        async with aiofiles.open(root / file.name, 'wb') as f:
            await f.write(file.body)

    if not found:
        return json(response_message(EINVAL, 'No files are found in the request'))

    if script_type == 'test_scripts':
        for name, file in request.files.items():
            if not file.name.endswith('.md'):
                continue
            ret = await db_update_test(root, file.name, user, organization, team)
            if not ret:
                return json(response_message(UNKNOWN_ERROR, 'Failed to update test suite'))
    return json(response_message(SUCCESS))

bp.add_route(ScriptView.as_view(), '/')
