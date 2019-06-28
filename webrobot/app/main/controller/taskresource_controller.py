import os
from pathlib import Path

import requests
from bson.objectid import ObjectId
from flask import request, send_from_directory
from flask_restplus import Resource
from mongoengine import ValidationError

from app.main.util.decorator import token_required, organization_team_required_by_args, task_required
from app.main.util.get_path import get_test_result_path, get_upload_files_root
from ..config import get_config
from ..model.database import *
from ..util.dto import TaskResourceDto
from ..util.tarball import make_tarfile, pack_files
from ..util.errors import *

api = TaskResourceDto.api

TARBALL_TEMP = Path('temp')


@api.route('/<task_id>')
@api.param('task_id', 'task id to process')
class TaskResourceController(Resource):
    # @token_required
    def get(self, task_id):
        try:
            task = Task.objects(pk=task_id).get() 
        except ValidationError as e:
            print(e)
            return error_message(EINVAL, 'Task ID incorrect'), 400
        except Task.DoesNotExist:
            return error_message(ENOENT, 'Task not found'), 404
        
        if not task.upload_dir:
            return error_message(SUCCESS, 'Upload directory is empty'), 406

        upload_root = get_upload_files_root(task)
        result_root = get_test_result_path(task)

        if request.args.get('file', None):
            return send_from_directory(Path(os.getcwd()) / upload_root, request.args['file'])

        tarball = pack_files(task_id, upload_root, result_root / TARBALL_TEMP)
        if not tarball:
            return error_message(EIO, 'Packing task resource files failed'), 401

        tarball = os.path.basename(tarball)
        return send_from_directory(Path(os.getcwd()) / result_root / TARBALL_TEMP, tarball)

@api.route('/list')
@api.param('task_id', 'task id to process')
class TaskResourceList(Resource):
    @token_required
    @organization_team_required_by_args
    @task_required
    def get(self, **kwargs):
        task = kwargs['task']
        if not task.upload_dir:
            return []

        upload_root = get_upload_files_root(task)
        if not os.path.exists(upload_root):
            return error_message(ENOENT, 'Task upload directory does not exist'), 404

        return os.listdir(upload_root)

@api.route('/')
class TaskResourceUpload(Resource):
    @token_required
    @api.doc('upload resource files associated with a task, if no files uploaded yet, a new directory will be created')
    def post(self, user):
        found = False

        if 'resource_id' in request.form:
            temp_id = request.form['resource_id']
        else:
            temp_id = str(ObjectId())
            os.mkdir(UPLOAD_DIR / temp_id)
        upload_root = UPLOAD_DIR / temp_id

        for name, file in request.files.items():
            found = True
            filename = upload_root / file.filename
            file.save(str(filename))

        files = request.form.getlist('file')
        for f in files:
            ret = requests.get(f)
            if ret.status_code == 200:
                found = True
                filename = f.split('?')[1].split('=')[1]
                filename = upload_root / filename
                with open(filename, 'wb') as fp:
                    fp.write(ret.content)

        if not found:
            return error_message(ENOENT, 'No files are found in the request'), 404

        return {'status': 0, 'data': temp_id}
