import os
import re
import shutil
from pathlib import Path

from flask import Flask, send_from_directory, request, current_app
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
_update_script = ScriptDto.update_script
_delete_script = ScriptDto.delete_script
_upload_scripts = ScriptDto.upload_scripts

@api.route('/')
@api.response(404, 'Scripts not found.')
class ScriptManagement(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('return script list or script file')
    @api.param('organization', description='The organization ID')
    @api.param('team', description='The team ID')
    @api.param('file', description='Path to the queried file')
    @api.param('script_type', description='File type {user_scripts | backing_scripts}')
    def get(self, **kwargs):
        """
        A compound get method for returning script file list or script file content
        
        When field file is None, return the file list as per script_type, otherwise return the specified file.
        """
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
    @api.doc('update file content')
    @api.expect(_update_script)
    def post(self, **kwargs):
        """Update the script file content"""
        script = request.json.get('file', None)
        if not script:
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

        dirname = os.path.dirname(script)
        basename = os.path.basename(script)
        try:
            os.makedirs(root / dirname)
        except FileExistsError:
            pass

        if content or content == '':
            if script_type == 'user_scripts':
                content = re.sub(r'\\([{}*_\.])', r'\1', content)
            elif script_type == 'backing_scripts':
                content = re.sub(r'\r\n', '\n', content)

            if basename:
                with open(root / script, 'w', encoding='utf-8') as f:
                    f.write(content)

        if new_name:
            if basename:
                Test.objects(path=os.path.abspath(root / script)).delete()
                os.rename(root / script, root / dirname / new_name)
            else:
                os.rename(root / script, root / os.path.dirname(dirname) / new_name)

        if basename and script_type == 'user_scripts':
            _script = str(Path(dirname) / new_name) if new_name else script
            if _script.endswith('.md'):
                ret = db_update_test(scripts_dir=root, script=_script, user=user.email, organization=organization, team=team)
                if ret:
                    return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401

        return error_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('delete the file')
    @api.expect(_delete_script)
    def delete(self, **kwargs):
        """Delete the script file"""
        organization = kwargs['organization']
        team = kwargs['team']
        
        script = request.json.get('file', None)
        if not script:
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
            return error_message(ENOENT, 'File/directory doesn\'t exist'), 404

        if os.path.isfile(root / script):
            try:
                os.remove(root / script)
            except OSError as err:
                current_app.logger.exception(err)
                return error_message(EIO, 'Error happened while deleting a file'), 401

            if script_type == 'user_scripts':
                cnt = Test.objects(path=os.path.abspath(root / script)).delete()
                if cnt == 0:
                    return error_message(ENOENT, 'Test suite not found in the database'), 404
        else:
            try:
                Test.objects(path__contains=os.path.abspath(root / script)).delete()
                shutil.rmtree(root / script)
            except OSError as err:
                current_app.logger.exception(err)
                return error_message(EIO, 'Error happened while deleting a directory'), 401

        return error_message(SUCCESS)

@api.route('/upload/')
class ScriptUpload(Resource):
    @token_required
    @organization_team_required_by_form
    @api.doc('upload the scripts')
    @api.expect(_upload_scripts)
    def post(self, **kwargs):
        """
        Upload the scripts

        Note: Files in the form request payload are tuples of file name and file content
        which can't be explicitly listed here. Please check out the form data format on the web.
        Usually browser will take care of it.
        """
        found = False

        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        
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
            for name, file in request.files.items():
                ret = db_update_test(scripts_dir=root, script=file.filename, user=user.email, organization=organization, team=team)
                if ret:
                    return error_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401
