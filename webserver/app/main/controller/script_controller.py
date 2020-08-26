import os
import re
import shutil
from pathlib import Path

from flask import send_from_directory, request, current_app
from flask_restx import Resource

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form
from app.main.util.get_path import get_user_scripts_root, get_back_scripts_root, is_path_secure
from task_runner.util.dbhelper import db_update_test
from ..config import get_config
from ..model.database import Test, Package
from ..util.dto import ScriptDto
from ..util.tarball import path_to_dict
from ..util.response import response_message, EINVAL, ENOENT, UNKNOWN_ERROR, SUCCESS, EIO

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

        test_libraries_root = get_back_scripts_root(team=team, organization=organization)
        test_scripts_root = get_user_scripts_root(team=team, organization=organization)

        if script_path:
            if script_type is None:
                return response_message(EINVAL, 'Field script_type is required'), 400
            if script_type == 'test_scripts':
                return send_from_directory(Path(os.getcwd()) / test_scripts_root, script_path)
            elif script_type == 'test_libraries':
                return send_from_directory(Path(os.getcwd()) / test_libraries_root, script_path)
            else:
                return response_message(EINVAL, 'Unsupported script type ' + script_type), 400
        elif script_type:
            return response_message(EINVAL, 'Field file is required'), 400

        test_scripts = path_to_dict(test_scripts_root)
        test_libraries = path_to_dict(test_libraries_root)
        return {'test_scripts': test_scripts, 'test_libraries': test_libraries}

    @token_required
    @organization_team_required_by_json
    @api.doc('update file content')
    @api.expect(_update_script)
    def post(self, **kwargs):
        """Update the script file content"""
        script = request.json.get('file', None)
        if not script:
            return response_message(EINVAL, 'Field file is required'), 400
        if not is_path_secure(script):
            return response_message(EINVAL, 'Illegal file path'), 401

        new_name = request.json.get('new_name', None)
        if new_name:
            if not is_path_secure(new_name):
                return response_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return response_message(EINVAL, 'Field script_type is required'), 400

        content = request.json.get('content', None)
        if content is None and new_name is None:
            return response_message(EINVAL, 'Field content is required'), 400

        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        package = None
        
        if script_type == 'test_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'test_libraries':
            root = get_back_scripts_root(team=team, organization=organization)
        else:
            return response_message(EINVAL, 'Unsupported script type ' + script_type), 400

        dirname = os.path.dirname(script)
        basename = os.path.basename(script)

        if script_type == 'test_scripts' and basename.endswith('.md'):
            test = Test.objects(test_suite=os.path.splitext(basename)[0], path=dirname, organization=organization, team=team).first()
        elif script_type == 'test_libraries' and dirname:
            package = Package.objects(py_packages=dirname).first()
            if not package:
                return response_message(ENOENT, 'package not found'), 404

        try:
            os.makedirs(root / dirname)
        except FileExistsError:
            pass

        if content or content == '':
            if script_type == 'test_scripts':
                content = re.sub(r'\\([{}*_\.])', r'\1', content)
            elif script_type == 'test_libraries':
                content = re.sub(r'\r\n', '\n', content)

            if basename:
                with open(root / script, 'w', encoding='utf-8') as f:
                    f.write(content)

        if new_name:
            if basename:
                new_path = os.path.join(dirname, new_name)
                os.rename(root / script, root / new_path)
                if script_type == 'test_scripts' and test:
                    test.modify(test_suite=os.path.splitext(new_name)[0])
            else:
                os.rename(root / script, root / os.path.dirname(dirname) / new_name)

        if basename and script_type == 'test_scripts':
            _script = str(Path(dirname) / new_name) if new_name else script
            if _script.endswith('.md'):
                ret = db_update_test(root, _script, user, organization, team)
                if not ret:
                    return response_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401

        if script_type == 'test_libraries' and package:
            package.modify(modified=True)

        return response_message(SUCCESS)

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
            return response_message(EINVAL, 'Field file is required'), 400
        if not is_path_secure(script):
            return response_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401

        dirname = os.path.dirname(script)
        basename = os.path.basename(script)

        script_type = request.json.get('script_type', None)
        if script_type is None:
            return response_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'test_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'test_libraries':
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
                return response_message(EIO, 'Error happened while deleting the file'), 401

            if script_type == 'test_scripts':
                Test.objects(test_suite=os.path.splitext(basename)[0], path=dirname, organization=organization, team=team).delete()
        else:
            if script_type == 'test_scripts':
                cnt = Test.objects(path__startswith=dirname, organization=organization, team=team).delete()
                if cnt == 0:
                    current_app.logger.error(f'Test suite not found in the database under the path {dirname}')
            try:
                shutil.rmtree(root / script)
            except OSError as err:
                current_app.logger.exception(err)
                return response_message(EIO, 'Error happened while deleting the directory'), 401

        return response_message(SUCCESS)

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
            return response_message(EINVAL, 'Field script_type is required'), 400

        if script_type == 'test_scripts':
            root = get_user_scripts_root(team=team, organization=organization)
        elif script_type == 'test_libraries':
            root = get_back_scripts_root(team=team, organization=organization)
        else:
            return response_message(EINVAL, 'Unsupported script type ' + script_type), 400

        if not os.path.exists(root):
            os.mkdir(root)

        for name, file in request.files.items():
            if not is_path_secure(file.filename):
                return response_message(EINVAL, 'Referencing to Upper level directory is not allowed'), 401
            found = True
            filename = root / file.filename
            file.save(str(filename))

        if not found:
            return response_message(EINVAL, 'No files are found in the request'), 401

        if script_type == 'test_scripts':
            for name, file in request.files.items():
                if not file.filename.endswith('.md'):
                    continue
                ret = db_update_test(root, file.filename, user, organization, team)
                if not ret:
                    return response_message(UNKNOWN_ERROR, 'Failed to update test suite'), 401
