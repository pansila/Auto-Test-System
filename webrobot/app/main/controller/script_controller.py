import os
import re
import shutil
from pathlib import Path

from flask import Flask, send_from_directory, request
from flask_restplus import Resource

from app.main.util.decorator import token_required
from app.main.util.request_parse import parse_organization_team
from task_runner.util.dbhelper import db_update_test
from ..config import get_config
from ..model.database import *
from ..util.dto import ScriptDto
from ..util.tarball import path_to_dict
from ..util.errors import *

api = ScriptDto.api

TARBALL_TEMP = Path('temp')
USERS_ROOT = Path(get_config().USERS_ROOT)
BACKING_SCRIPT_ROOT = Path(get_config().BACKING_SCRIPT_ROOT)
USER_SCRIPT_ROOT = Path(get_config().USER_SCRIPT_ROOT)

@api.route('/')
@api.response(404, 'Scripts not found.')
class ScriptManagement(Resource):
    @token_required
    @api.doc('compound get method for script file list and script file content')
    def get(self, user):
        script_path = request.args.get('file', default=None)
        script_type = request.args.get('script_type', default=None)

        ret = parse_organization_team(user, request.args)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret
        
        user_scripts_root = Path(os.getcwd()) / USERS_ROOT / organization.path / USER_SCRIPT_ROOT
        backing_scripts_root = Path(os.getcwd()) / USERS_ROOT / organization.path / BACKING_SCRIPT_ROOT

        if script_path:
            if script_type is None:
                return error_message(EINVAL, 'Field script_type is required'), 400
            if script_type == 'user_scripts':
                return send_from_directory(user_scripts_root, script_path)
            elif script_type == 'backing_scripts':
                return send_from_directory(backing_scripts_root, script_path)
            else:
                return error_message(EINVAL, 'Unsupported script type ' + script_type), 400
        elif script_type:
            return error_message(EINVAL, 'Field file is required'), 400

        user_scripts = path_to_dict(user_scripts_root)
        backing_scripts = path_to_dict(backing_scripts_root)
        return {'user_scripts': user_scripts, 'backing_scripts': backing_scripts}

    @token_required
    def post(self, user):
        script = request.json.get('file', None)
        if script is None or script == '':
            return error_message(EINVAL, 'Field file is required'), 400
        if '..' in script:
            return error_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        new_name = request.json.get('new_name', None)
        if new_name:
            if '..' in new_name:
                return error_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        content = request.json.get('content', None)
        if content is None and new_name is None:
            return error_message(EINVAL, 'Field content is required'), 400

        ret = parse_organization_team(user, request.json)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret
        
        if content:
            if script_type == 'user_scripts':
                content = re.sub(r'\\', '', content)
            elif script_type == 'backing_scripts':
                content = re.sub(r'\r\n', '\n', content)

            if script_type == 'user_scripts':
                root = Path(os.getcwd()) / USERS_ROOT / organization.path / USER_SCRIPT_ROOT
            elif script_type == 'backing_scripts':
                root = Path(os.getcwd()) / USERS_ROOT / organization.path / BACKING_SCRIPT_ROOT
            else:
                return error_message(EINVAL, 'Unsupported script type ' + script_type), 400

            dirname = os.path.dirname(script)
            try:
                os.makedirs(root / dirname)
            except FileExistsError:
                pass

            if dirname != script:
                with open(root / script, 'w') as f:
                    f.write(content)

        if new_name:
            os.rename(USER_SCRIPT_ROOT / script, USER_SCRIPT_ROOT / os.path.dirname(script) / new_name)

        if script_type == 'user_scripts':
            _script = str(Path(os.path.dirname(script)) / new_name) if new_name else script
            ret = db_update_test(scripts_dir=root, script=_script, user=user['email'], organization=organization, team=team)
            if ret:
                return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401

    @token_required
    def delete(self, user):
        ret = parse_organization_team(user, request.json)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret
        
        script = request.json.get('file', None)
        if script is None or script == '':
            return error_message(EINVAL, 'Field file is required'), 400
        if '..' in script:
            return error_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'user_scripts':
            root = Path(os.getcwd()) / USERS_ROOT / organization.path / USER_SCRIPT_ROOT
        elif script_type == 'backing_scripts':
            root = Path(os.getcwd()) / USERS_ROOT / organization.path / BACKING_SCRIPT_ROOT
        else:
            return error_message(EINVAL, 'Unsupported script type ' + script_type), 400

        if not os.path.exists(root / script):
            return error_message(ENOENT, 'file/directory doesn\'t exist'), 404

        if os.path.isfile(root / script):
            try:
                os.remove(root / script)
            except OSError as err:
                print(err)
                return error_message(EIO, 'Error happened while deleting a file: '), 401
        else:
            try:
                shutil.rmtree(root / script)
            except OSError as err:
                print(err)
                return error_message(EIO, 'Error happened while deleting a directory'), 401

        if script_type == 'user_scripts':
            cnt = Test.objects(path=str(root / script)).delete()
            if cnt == 0:
                return error_message(ENOENT, 'Failed to delete test suite'), 404

@api.route('/upload/')
class ScriptUpload(Resource):
    @token_required
    @api.doc('upload the scripts')
    def post(self, user):
        found = False

        ret = parse_organization_team(user, request.form)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret
        
        script_type = request.form.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        script_type = request.form.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'user_scripts':
            root = Path(os.getcwd()) / USERS_ROOT / organization.path / USER_SCRIPT_ROOT
        elif script_type == 'backing_scripts':
            root = Path(os.getcwd()) / USERS_ROOT / organization.path / BACKING_SCRIPT_ROOT
        else:
            return error_message(EINVAL, 'Unsupported script type ' + script_type), 400

        if not os.path.exists(root):
            os.mkdir(root)

        for name, file in request.files.items():
            if '..' in file.filename:
                return error_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401
            found = True
            filename = root / file.filename
            file.save(str(filename))

        if not found:
            return error_message(ENOENT, 'No files are found in the request'), 404

        if script_type == 'user_scripts':
            ret = db_update_test(scripts_dir=root, script=file.filename, user=user['email'], organization=organization, team=team)
            if ret:
                return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401
