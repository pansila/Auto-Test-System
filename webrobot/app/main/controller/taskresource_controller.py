import os
from pathlib import Path

from bson.objectid import ObjectId
from flask import request, send_from_directory
from flask_restplus import Resource
from mongoengine import ValidationError

from ..config import get_config
from ..model.database import (QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                              QUEUE_PRIORITY_MIN, Task, TaskQueue, Test)
from ..util.dto import TaskResourceDto
from ..util.tarball import make_tarfile, pack_files

api = TaskResourceDto.api

TARBALL_TEMP = Path('temp')
UPLOAD_DIR = Path(get_config().UPLOAD_ROOT)

@api.route('/<task_id>')
@api.param('task_id', 'task id to process')
class TaskResourceController(Resource):
    @api.response(406, "Task resource doesn't exist.")
    def get(self, task_id):
        try:
            task = Task.objects(pk=task_id).get()
        except ValidationError:
            api.abort(404)
        except Task.DoesNotExist:
            api.abort(404)
        
        if task.upload_dir == '' or task.upload_dir == None:
            api.abort(406)

        tarball = pack_files(task_id, UPLOAD_DIR / task.upload_dir, TARBALL_TEMP)
        if not tarball:
            api.abort(404)
        else:
            tarball = os.path.basename(tarball)
            return send_from_directory(Path(os.getcwd()) / TARBALL_TEMP, tarball)

@api.route('/')
class TaskResourceInitUpload(Resource):
    @api.doc('upload some resource associated with a task')
    def post(self):
        upload_dir = Path(get_config().UPLOAD_ROOT)
        found = False

        try:
            os.mkdir(upload_dir)
        except FileExistsError:
            pass

        if 'resource_id' in request.form:
            temp_id = request.form['resource_id']
        else:
            temp_id = str(ObjectId())
            os.mkdir(upload_dir / temp_id)

        for name, file in request.files.items():
            found = True
            filename = upload_dir / temp_id / file.filename
            file.save(str(filename))

        if not found:
            print('No files are found in the request')
            api.abort(404)

        return {'status': 0, 'data': temp_id}
