import os
import shutil
from pathlib import Path

from bson.objectid import ObjectId
from flask import request, send_from_directory, current_app
from flask_restx import Resource
from mongoengine import ValidationError

from app.main.util.decorator import token_required, organization_team_required_by_args, task_required, organization_team_required_by_form
from app.main.util.get_path import get_test_result_path, get_upload_files_root
from ..config import get_config
from ..model.database import Task
from ..util.dto import TaskResourceDto
from ..util.tarball import make_tarfile, pack_files
from ..util.response import response_message, EINVAL, ENOENT, SUCCESS, EIO

api = TaskResourceDto.api
_task_resource = TaskResourceDto.task_resource

TARBALL_TEMP = Path('temp')
UPLOAD_DIR = Path(get_config().UPLOAD_ROOT)


@api.route('/<task_id>')
@api.param('task_id', 'task id to process')
class TaskResourceController(Resource):
    # @token_required
    @api.doc('return the test result files')
    def get(self, task_id):
        """
        Return the test result files
        
        If a file name specified, a file in the upload directory will be returned
        If a file name is not specified, return the bundled file that contains all result files
        """
        try:
            task = Task.objects(pk=task_id).get() 
        except ValidationError as e:
            current_app.logger.exception(e)
            return response_message(EINVAL, 'Task ID incorrect'), 400
        except Task.DoesNotExist:
            return response_message(ENOENT, 'Task not found'), 404
        
        if not task.upload_dir:
            return response_message(SUCCESS, 'Upload directory is empty'), 406

        upload_root = get_upload_files_root(task)
        result_root = get_test_result_path(task)

        upload_file = request.args.get('file', None)
        if upload_file:
            return send_from_directory(Path(os.getcwd()) / upload_root, upload_file)

        tarball = pack_files(task_id, upload_root, result_root / TARBALL_TEMP)
        if not tarball:
            return response_message(EIO, 'Packing task resource files failed'), 401

        tarball = os.path.basename(tarball)
        return send_from_directory(Path(os.getcwd()) / result_root / TARBALL_TEMP, tarball)

@api.route('/list')
@api.param('task_id', 'task id to process')
class TaskResourceList(Resource):
    @token_required
    @organization_team_required_by_args
    @task_required
    @api.doc('get the upload file list')
    @api.param('organization', description='The organization ID')
    @api.param('team', description='The team ID')
    @api.param('task_id', description='The task ID')
    def get(self, **kwargs):
        """Get the file list in the upload directory"""
        task = kwargs['task']
        if not task.upload_dir:
            return []

        upload_root = get_upload_files_root(task)
        if not os.path.exists(upload_root):
            return response_message(ENOENT, 'Task upload directory does not exist'), 404

        return os.listdir(upload_root)

@api.route('/')
class TaskResourceUpload(Resource):
    @token_required
    @organization_team_required_by_form
    @api.doc('upload resource files')
    @api.expect(_task_resource)
    def post(self, **kwargs):
        """
        Upload resource files
        
        If no files uploaded yet, a temporary directory will be created to accommodate the files
        """
        organization = kwargs['organization']
        team = kwargs['team']
        found = False

        temp_id = request.form.get('resource_id', None)
        if not temp_id:
            temp_id = str(ObjectId())
            os.mkdir(UPLOAD_DIR / temp_id)
        upload_root = UPLOAD_DIR / temp_id

        for name, file in request.files.items():
            found = True
            filename = upload_root / file.filename
            file.save(str(filename))

        files = request.form.getlist('file')
        if len(files) > 0:
            retrigger_task_id = request.form.get('retrigger_task', None)
            if not retrigger_task_id:
                return response_message(EINVAL, 'Field retrigger_task is required'), 400

            retrigger_task = Task.objects(pk=retrigger_task_id).first()
            if not retrigger_task:
                return response_message(ENOENT, 'Re-trigger task not found'), 404

            if retrigger_task.test.organization != organization or retrigger_task.test.team != team:
                return response_message(EINVAL, 'Re-triggering a task not belonging to your organization/team is not allowed'), 403

            retrigger_task_upload_root = get_upload_files_root(retrigger_task)
            if not os.path.exists(retrigger_task_upload_root):
                return response_message(ENOENT, 'Re-trigger task upload directory does not exist'), 404

        for f in files:
            try:
                shutil.copy(retrigger_task_upload_root / f, upload_root)
                found = True
            except FileNotFoundError:
                shutil.rmtree(upload_root)
                return response_message(ENOENT, 'File {} used in the re-triggered task not found'.format(f)), 404

        if not found:
            return response_message(ENOENT, 'No files are found in the request'), 404

        return response_message(SUCCESS, resource_id=temp_id), 200
