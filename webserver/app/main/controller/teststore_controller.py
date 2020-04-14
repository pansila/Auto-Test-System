import os
import re
import shutil
import zipfile
from pathlib import Path
from pkg_resources import parse_version

from flask import send_from_directory, request, current_app
from flask_restx import Resource

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form
from app.main.util.get_path import get_test_store_root, is_path_secure, get_user_scripts_root, get_back_scripts_root, get_package_name
from task_runner.util.dbhelper import get_package_info
from ..config import get_config
from ..model.database import *
from ..util.dto import StoreDto
from ..util.tarball import path_to_dict
from ..util.response import *
from ..util import js2python_bool

api = StoreDto.api
_upload_package = StoreDto.upload_package
_delete_package = StoreDto.delete_package

@api.route('/')
class ScriptManagement(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('return script list or script file')
    def get(self, **kwargs):
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']
        data = request.args
        page = data.get('page', default=1)
        limit = data.get('limit', default=10)
        title = data.get('title', default=None)

        page = int(page)
        limit = int(limit)
        if page <= 0 or limit <= 0:
            return response_message(EINVAL, 'Field page and limit should be larger than 1'), 400

        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400

        if title:
            query = {'name__contains': title, 'proprietary': proprietary, 'package_type': package_type}
        else:
            query = {'proprietary': proprietary, 'package_type': package_type}

        packages = Package.objects(**query)
        ret = []
        p = re.compile(r'\d+\.\d+\.\d+')
        for package in packages[(page-1)*limit:page*limit]:
            ret.append({
                'name': package.name,
                'summary': package.description,
                'description': package.long_description,
                'stars': package.rating,
                'download_times': package.download_times,
                'versions': list(reversed(sorted(map(lambda x: p.search(x).group(), package.files), key=parse_version)))
            })
        return {'items': ret, 'total': packages.count()}

    @token_required
    @organization_team_required_by_form
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

        data = request.form
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        
        root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        if not os.path.exists(root):
            os.mkdir(root)

        query = {'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization
            query['team'] = team

        for name, file in request.files.items():
            if not is_path_secure(file.filename):
                return response_message(EINVAL, 'Illegal file name'), 401
            found = True
            filename = str(root / file.filename)
            file.save(filename)

            name, pkg_name, description, long_description = get_package_info(filename)
            if not name:
                os.unlink(filename)
                return response_message(EINVAL, 'Package name not found'), 401

            package = Package.objects(name=name, **query).first()
            if not package:
                package = Package(name=name, **query)

            if proprietary:
                package.organization = organization
                package.team = team
            try:
                os.mkdir(root / pkg_name)
            except FileExistsError:
                pass
            shutil.move(filename, root / pkg_name / file.filename)
            package.description = description
            package.long_description = long_description
            if file.filename not in package.files:
                package.files.append(file.filename)
            package.save()

        if not found:
            return response_message(EINVAL, 'File not found'), 404

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('install the package')
    @api.expect(_upload_package)
    def put(self, **kwargs):
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        package_info = data.get('package', None)
        if not package_info:
            return response_message(EINVAL, 'Field package is required'), 400
        version = data.get('version', None)
        if not version:
            return response_message(EINVAL, 'Field version is required'), 400
        
        root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        if not os.path.exists(root):
            os.mkdir(root)

        query = {'proprietary': proprietary, 'package_type': package_type, 'name': package_info['name']}
        if proprietary:
            query['organization'] = organization
            query['team'] = team

        package = Package.objects(**query).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404

        if package_type == 'Test Suite':
            package_name = get_package_name(package.name).lower()
            pkg_name = package_name.lower()

            scripts_root = get_user_scripts_root(organization=organization, team=team)
            try:
                shutil.rmtree(scripts_root / pkg_name)
            except FileNotFoundError:
                pass

            libraries_root = get_back_scripts_root(organization=organization, team=team)
            try:
                shutil.rmtree(libraries_root / pkg_name)
            except FileNotFoundError:
                pass

            with zipfile.ZipFile(root / package_name / package.get_package_by_version(version)) as fp:
                libraries = (f for f in fp.namelist() if f.startswith(pkg_name + '/') and not f.startswith(pkg_name + '/scripts/'))
                for l in libraries:
                    fp.extract(l, libraries_root)
                scripts = (f for f in fp.namelist() if f.startswith(pkg_name + '/scripts/'))
                for s in scripts:
                    fp.extract(s, scripts_root)
                for f in os.listdir(scripts_root / pkg_name / 'scripts'):
                    shutil.move(str(scripts_root / pkg_name / 'scripts' / f), scripts_root / pkg_name)
                shutil.rmtree(scripts_root / pkg_name / 'scripts')

        package.modify(inc__download_times=1)

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
        if not is_path_secure(script):
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
