import os
from mongoengine import ValidationError
from flask import request, send_from_directory
from flask_restplus import Resource
from pathlib import Path
from bson.objectid import ObjectId

from ..util.dto import TaskResourceDto
from ..util.tarball import make_tarfile, pack_files
from ..model.database import Test, Task, TaskQueue, QUEUE_PRIORITY_MIN, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX
from ..config import get_config

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
        temp_id = str(ObjectId())

        name = request.form['name']
        if name[0] == '"' or name[0] == "'":
            name = name[1:-1]

        file = request.files['resource']

        try:
            os.mkdir(upload_dir)
        except FileExistsError:
            pass

        os.mkdir(upload_dir / temp_id)
        filename = upload_dir / temp_id / name
        file.save(str(filename))

        return {'status': 0, 'data': temp_id}

@api.route('/<resource_id>')
@api.param('resource_id', 'resource id to proceed')
class TaskResourceFollowingUpload(Resource):
    @api.response(201, 'Task resource successfully uploaded.')
    @api.doc('upload some resource associated with a task')
    def post(self, resource_id):
        upload_dir = Path(get_config().UPLOAD_ROOT)

        name = request.form['name']
        if name[0] == '"' or name[0] == "'":
            name = name[1:-1]

        file = request.files['resource']

        if not os.path.exists(upload_dir) or not os.path.exists(upload_dir / resource_id):
            api.abort(404)
        filename = upload_dir / resource_id / name
        file.save(str(filename))

        return {'status': 0, 'data': resource_id}
