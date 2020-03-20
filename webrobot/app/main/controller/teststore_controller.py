import os
import re
import shutil
from pathlib import Path

from flask import send_from_directory, request, current_app
from flask_restplus import Resource

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form, organization_team_by_form
from app.main.util.get_path import get_test_store_root
from task_runner.util.dbhelper import db_update_package
from ..config import get_config
from ..model.database import *
from ..util.dto import StoreDto
from ..util.tarball import path_to_dict
from ..util.response import *

api = StoreDto.api
_upload_package = StoreDto.upload_package
_delete_package = StoreDto.delete_package

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
                return response_message(EINVAL, 'Field script_type is required'), 400
            if script_type == 'user_scripts':
                return send_from_directory(Path(os.getcwd()) / user_scripts_root, script_path)
            elif script_type == 'backing_scripts':
                return send_from_directory(Path(os.getcwd()) / back_scripts_root, script_path)
            else:
                return response_message(EINVAL, 'Unsupported script type ' + script_type), 400
        elif script_type:
            return response_message(EINVAL, 'Field file is required'), 400

        user_scripts = path_to_dict(user_scripts_root)
        back_scripts = path_to_dict(back_scripts_root)
        return {'user_scripts': user_scripts, 'backing_scripts': back_scripts}

    @token_required
    @organization_team_by_form
    @api.doc('upload the package')
    @api.expect(_upload_package)
    def post(self, **kwargs):
        """
        Upload the package

        Note: Files in the form request payload are tuples of file name and file content
        which can't be explicitly listed here. Please check out the form data format on the web.
        Usually browser will take care of it.
        """
        found = False

        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        
        root = get_test_store_root(team=team, organization=organization)
        if not os.path.exists(root):
            os.mkdir(root)

        for name, file in request.files.items():
            if '..' in file.filename:
                return response_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401
            found = True
            filename = root / file.filename
            file.save(str(filename))

        if not found:
            return response_message(ENOENT, 'No files are found in the request'), 404

        for name, file in request.files.items():
            ret = db_update_package(pkg_dir=root, script=file.filename, user=user.email, organization=organization, team=team)
            if ret:
                return response_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('delete the file')
    @api.expect(_delete_package)
    def delete(self, **kwargs):
        """Delete the script file"""
        organization = kwargs['organization']
        team = kwargs['team']
        
        script = request.json.get('file', None)
        if not script:
            return response_message(EINVAL, 'Field file is required'), 400
        if '..' in script:
            return response_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return response_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'user_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'backing_scripts':
            root = get_back_scripts_root(team=team, organization=organization)
        else:
            return response_message(EINVAL, 'Unsupported script type ' + script_type), 400

        if not os.path.exists(root / script):
            return response_message(ENOENT, 'File/directory doesn\'t exist'), 404

        if os.path.isfile(root / script):
            try:
                os.remove(root / script)
            except OSError as err:
                current_app.logger.exception(err)
                return response_message(EIO, 'Error happened while deleting a file'), 401

            if script_type == 'user_scripts':
                cnt = Test.objects(path=os.path.abspath(root / script)).delete()
                if cnt == 0:
                    return response_message(ENOENT, 'Test suite not found in the database'), 404
        else:
            try:
                Test.objects(path__contains=os.path.abspath(root / script)).delete()
                shutil.rmtree(root / script)
            except OSError as err:
                current_app.logger.exception(err)
                return response_message(EIO, 'Error happened while deleting a directory'), 401

        return response_message(SUCCESS)
