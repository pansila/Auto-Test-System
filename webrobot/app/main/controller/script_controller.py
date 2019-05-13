import os
import re
import shutil
from pathlib import Path

from flask import Flask, send_from_directory, request
from flask_restplus import Resource

from ..config import get_config
from ..model.database import Event, EventQueue, Test, EVENT_CODE_UPDATE_USER_SCRIPT
from ..util.dto import ScriptDto
from ..util.tarball import path_to_dict

api = ScriptDto.api

TARBALL_TEMP = Path('temp')
BACKING_SCRIPT_ROOT = Path(get_config().BACKING_SCRIPT_ROOT)
USER_SCRIPT_ROOT = Path(get_config().USER_SCRIPT_ROOT)

@api.route('/')
@api.response(404, 'Scripts not found.')
class ScriptManagement(Resource):
    def get(self):
        script_path = request.args.get('file', default=None)
        script_type = request.args.get('script_type', default=None)
        if script_path:
            if script_type is None:
                print('Field script_type is required')
                api.abort(404)
            if script_type == 'user_scripts':
                return send_from_directory(USER_SCRIPT_ROOT, script_path)
            elif script_type == 'backing_scripts':
                return send_from_directory(BACKING_SCRIPT_ROOT, script_path)
            else:
                print('Unsupported script type ' + script_type)
                api.abort(404)
        elif script_type:
            print('Field file is required')
            api.abort(404)

        user_scripts = path_to_dict(USER_SCRIPT_ROOT)
        backing_scripts = path_to_dict(BACKING_SCRIPT_ROOT)
        return {'user_scripts': user_scripts, 'backing_scripts': backing_scripts}

    def post(self):
        script = request.json.get('file', None)
        if script is None or script == '':
            print('field file is required')
            api.abort(404)
        if '..' in script:
            print('Referencing to Upper level directory is not allowed')
            api.abort(404)

        new_name = request.json.get('new_name', None)
        if new_name:
            if '..' in new_name:
                print('Referencing to Upper level directory is not allowed')
                api.abort(404)

        script_type = request.json.get('script_type', None)
        if script_type is None:
            print('field script_type is required')
            api.abort(404)

        content = request.json.get('content', None)
        if content is None and new_name is None:
            print('field content is required')
            api.abort(404)

        if content is not None:
            if script_type == 'user_scripts':
                content = re.sub(r'\\', '', content)
            elif script_type == 'backing_scripts':
                content = re.sub(r'\r\n', '\n', content)
            dirname = os.path.dirname(script)
            if not os.path.exists(USER_SCRIPT_ROOT / dirname):
                os.makedirs(USER_SCRIPT_ROOT / dirname)

            if script_type == 'user_scripts':
                root = USER_SCRIPT_ROOT
            elif script_type == 'backing_scripts':
                root = BACKING_SCRIPT_ROOT
            else:
                print('Unsupported script type ' + script_type)
                api.abort(404)

            with open(root / script, 'w') as f:
                f.write(content)
        
        if new_name:
            os.rename(USER_SCRIPT_ROOT / script, USER_SCRIPT_ROOT / os.path.dirname(script) / new_name)

        event = Event()
        event.code = EVENT_CODE_UPDATE_USER_SCRIPT
        event.message['script'] = str(Path(os.path.dirname(script)) / new_name) if new_name else script
        event.save()

        if EventQueue.push(event) is None:
            print('Pushing the event to event queue failed')
            api.abort(404)

    def delete(self):
        script = request.json.get('file', None)
        if script is None or script == '':
            print('field file is required')
            api.abort(404)
        if '..' in script:
            print('Referencing to Upper level directory is not allowed')
            api.abort(404)

        script_type = request.json.get('script_type', None)
        if script_type is None:
            print('field script_type is required')
            api.abort(404)

        if script_type == 'user_scripts':
            root = USER_SCRIPT_ROOT
        elif script_type == 'backing_scripts':
            root = BACKING_SCRIPT_ROOT
        else:
            print('Unsupported script type ' + script_type)
            api.abort(404)

        if not os.path.exists(root / script):
            print('file/directory {} doesn\'t exist'.format(root / script))
            return

        if os.path.isfile(root / script):
            try:
                os.remove(root / script)
            except OSError as err:
                print('Error happened while deleting a file: ' + str(err))
                api.abort(404)
        else:
            try:
                shutil.rmtree(root / script)
            except OSError as err:
                print('Error happened while deleting a directory: ' + str(err))
                api.abort(404)

@api.route('/upload/')
class ScriptUpload(Resource):
    @api.doc('upload the scripts')
    def post(self):
        found = False

        script_type = request.form.get('script_type', None)
        if script_type is None:
            print('field script_type is required')
            api.abort(404)

        if script_type == 'user_scripts':
            root = USER_SCRIPT_ROOT
        elif script_type == 'backing_scripts':
            root = BACKING_SCRIPT_ROOT
        else:
            print('Unsupported script type ' + script_type)
            api.abort(404)

        print(request.form)
        for name, file in request.files.items():
            print(name, file)
            found = True
            filename = root / file.filename
            file.save(str(filename))

        if not found:
            print('No files are found in the request')
            api.abort(404)
