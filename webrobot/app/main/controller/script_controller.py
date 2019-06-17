import os
import re
import shutil
from pathlib import Path

from flask import Flask, send_from_directory, request
from flask_restplus import Resource

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form
from app.main.util.get_path import get_user_scripts_root, get_back_scripts_root
from task_runner.util.dbhelper import db_update_test
from ..config import get_config
from ..model.database import *
from ..util.dto import ScriptDto
from ..util.tarball import path_to_dict
from ..util.errors import *

api = ScriptDto.api


@api.route('/')
@api.response(404, 'Scripts not found.')
class ScriptManagement(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('compound get method for script file list and script file content')
    def get(self, **kwargs):
        script_path = request.args.get('file', default=None)
        script_type = request.args.get('script_type', default=None)

        organization = kwargs['organization']
        team = kwargs['team']

        back_scripts_root = get_back_scripts_root(team=team, organization=organization)
        user_scripts_root = get_user_scripts_root(team=team, organization=organization)

        if script_path:
            if script_type is None:
                return error_message(EINVAL, 'Field script_type is required'), 400
            if script_type == 'user_scripts':
                return send_from_directory(Path(os.getcwd()) / user_scripts_root, script_path)
            elif script_type == 'backing_scripts':
                return send_from_directory(Path(os.getcwd()) / back_scripts_root, script_path)
            else:
                return error_message(EINVAL, 'Unsupported script type ' + script_type), 400
        elif script_type:
            return error_message(EINVAL, 'Field file is required'), 400

        user_scripts = path_to_dict(user_scripts_root)
        back_scripts = path_to_dict(back_scripts_root)
        return {'user_scripts': user_scripts, 'backing_scripts': back_scripts}

    @token_required
    @organization_team_required_by_json
    def post(self, **kwargs):
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

        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        
        if script_type == 'user_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'backing_scripts':
            root = get_back_scripts_root(team=team, organization=organization)
        else:
            return error_message(EINVAL, 'Unsupported script type ' + script_type), 400

        if content:
            if script_type == 'user_scripts':
                content = re.sub(r'\\([{}_])', r'\1', content)
            elif script_type == 'backing_scripts':
                content = re.sub(r'\r\n', '\n', content)

            dirname = os.path.dirname(script)
            try:
                os.makedirs(root / dirname)
            except FileExistsError:
                pass

            if dirname != script:
                with open(root / script, 'w') as f:
                    f.write(content)

        if new_name:
            os.rename(root / script, root / os.path.dirname(script) / new_name)

        if script_type == 'user_scripts':
            _script = str(Path(os.path.dirname(script)) / new_name) if new_name else script
            ret = db_update_test(scripts_dir=root, script=_script, user=user.email, organization=organization, team=team)
            if ret:
                return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401

    @token_required
    @organization_team_required_by_json
    def delete(self, **kwargs):
        organization = kwargs['organization']
        team = kwargs['team']
        
        script = request.json.get('file', None)
        if script is None or script == '':
            return error_message(EINVAL, 'Field file is required'), 400
        if '..' in script:
            return error_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'user_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'backing_scripts':
            root = get_back_scripts_root(team=team, organization=organization)
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
    @organization_team_required_by_form
    @api.doc('upload the scripts')
    def post(self, **kwargs):
        found = False

        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        
        script_type = request.form.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        script_type = request.form.get('script_type', None)
        if script_type is None:
            return error_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'user_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'backing_scripts':
            root = get_back_scripts_root(team=team, organization=organization)
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
            ret = db_update_test(scripts_dir=root, script=file.filename, user=user.email, organization=organization, team=team)
            if ret:
                return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401
