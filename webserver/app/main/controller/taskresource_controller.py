import aiofiles
import os
from pathlib import Path
from bson.objectid import ObjectId

from async_files.utils import async_wraps
from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file, html
from sanic_openapi import doc

from app.main.util.decorator import token_required, organization_team_required_by_args, task_required, organization_team_required_by_form
from app.main.util.get_path import get_test_result_path, get_upload_files_root, is_path_secure
from ..config import get_config
from ..model.database import Task
from ..util import async_rmtree, async_copy, async_exists
from ..util.dto import TaskResourceDto, json_response
from ..util.tarball import pack_files, path_to_dict
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, EIO, NO_TASK_RESOURCES

_task_resource = TaskResourceDto.task_resource
_task_resource_response = TaskResourceDto.task_resource_response
_task_id = TaskResourceDto.task_id
_task_resource_file_list = TaskResourceDto.task_resource_file_list

TARBALL_TEMP = Path('temp')


bp = Blueprint('taskresource', url_prefix='/taskresource')

@bp.get('/<task_id>')
@doc.summary('return the test result files')
@doc.description('''\
    If a file name specified, a file in the upload directory will be returned
    If a file name is not specified, return the bundled file that contains all result files
''')
@doc.consumes('task_id', 'task id to process')
@doc.produces(201, doc.File())
@doc.produces(200, json_response)
# @token_required # TODO
async def handler(request, task_id):
    task = await Task.find_one({'_id': ObjectId(task_id)})
    if not task:
        return json(response_message(ENOENT, 'Task not found'))
    
    if not task.upload_dir:
        return json(response_message(NO_TASK_RESOURCES), status=204)

    upload_root = get_upload_files_root(task)
    result_root = await get_test_result_path(task)
    if not await async_exists(result_root / TARBALL_TEMP):
        await aiofiles.os.mkdir(result_root / TARBALL_TEMP)

    upload_file = request.args.get('file', None)
    if upload_file:
        return await file(upload_root / upload_file)

    tarball = await pack_files(task_id, upload_root, result_root / TARBALL_TEMP)
    if not tarball:
        return json(response_message(EIO, 'Packing task resource files failed'))

    tarball = os.path.basename(tarball)
    return await file(result_root / TARBALL_TEMP / tarball)

@bp.get('/list')
@doc.summary('Get the file list in the upload directory')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_task_id)
@doc.produces(_task_resource_file_list)
@token_required
@organization_team_required_by_args
@task_required
async def handler(request):
    task = request.ctx.task
    if not task.upload_dir:
        return []

    upload_root = get_upload_files_root(task)
    if not await async_exists(upload_root):
        return json(response_message(ENOENT, 'Task upload directory does not exist'))

    return json(response_message(SUCCESS, files=await async_wraps(path_to_dict)(upload_root)))

class TaskResourceView(HTTPMethodView):
    @doc.summary('upload resource files')
    @doc.description('If no files uploaded yet, a temporary directory will be created to accommodate the files')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_task_resource, location="formData", content_type="multipart/form-data")
    @doc.produces(_task_resource_response)
    @token_required
    @organization_team_required_by_form
    async def post(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        found = False

        temp_id = request.form.get('resource_id', None)
        if not temp_id:
            temp_id = str(ObjectId())
            await aiofiles.os.mkdir(request.app.config.UPLOAD_ROOT / temp_id)
        upload_root = request.app.config.UPLOAD_ROOT / temp_id

        for name, file in request.files.items():
            if not is_path_secure(file.name):
                return json(response_message(EINVAL, 'saving file with an illegal file name'))
            found = True
            async with aiofiles.open(upload_root / file.name, 'wb') as f:
                await f.write(file.body)

        files = request.form.getlist('file')
        if len(files) > 0:
            retrigger_task_id = request.form.get('retrigger_task', None)
            if not retrigger_task_id:
                return json(response_message(EINVAL, 'Field retrigger_task is required'))

            retrigger_task = await Task.find_one({'_id': ObjectId(retrigger_task_id)})
            if not retrigger_task:
                return json(response_message(ENOENT, 'Re-trigger task not found'))

            test = await retrigger_task.test.fetch()
            if test.organization != organization or test.team != team:
                return json(response_message(EINVAL, 'Re-triggering a task not belonging to your organization/team is not allowed'))

            retrigger_task_upload_root = get_upload_files_root(retrigger_task)
            if not await async_exists(retrigger_task_upload_root):
                return json(response_message(ENOENT, 'Re-trigger task upload directory does not exist'))

        for f in files:
            try:
                await async_copy(retrigger_task_upload_root / f, upload_root)
                found = True
            except FileNotFoundError:
                await async_rmtree(upload_root)
                return json(response_message(ENOENT, 'File {} used in the re-triggered task not found'.format(f)))

        if not found:
            return json(response_message(ENOENT, 'No files are found in the request'))

        return json(response_message(SUCCESS, resource_id=temp_id))

bp.add_route(TaskResourceView.as_view(), '/')
