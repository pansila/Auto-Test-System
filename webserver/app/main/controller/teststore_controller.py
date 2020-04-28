import datetime
import os
import re
import shutil
import tempfile
import zipfile
import distutils.core
from pathlib import Path
from pkg_resources import parse_version

from flask import send_from_directory, request, current_app
from flask_restx import Resource

from ..util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form, token_required_if_proprietary
from ..util.get_path import get_test_store_root, is_path_secure, get_user_scripts_root, get_back_scripts_root
from task_runner.util.dbhelper import get_package_info, get_package_requires, install_test_suite, get_internal_packages
from ..config import get_config
from ..model.database import Package, Test
from ..util.dto import StoreDto
from ..util.tarball import path_to_dict
from ..util.response import response_message, ENOENT, EINVAL, SUCCESS, EIO, EPERM
from ..util import js2python_bool

api = StoreDto.api
_upload_package = StoreDto.upload_package
_delete_package = StoreDto.delete_package
_packages = StoreDto.packages

SCRIPT_FILES_FIND = re.compile(r'^.*?/scripts/.*$').match

@api.route('/')
class PackageManagement(Resource):
    @token_required_if_proprietary
    @api.doc('return the package list')
    @api.marshal_list_with(_packages)
    def get(self, **kwargs):
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

        ret = []
        top_packages = Package.objects(name='Robot-Test-Utility', package_type=package_type, proprietary=False)
        for package in top_packages:
            ret.append({
                'name': package.name,
                'summary': package.description,
                'description': package.long_description,
                'stars': package.stars,
                'download_times': package.download_times,
                'package_type': package.package_type,
                'versions': package.versions,
                'upload_date': package.upload_date
            })

        packages = Package.objects(**query)
        p = re.compile(r'\d+\.\d+\.\d+')
        for package in packages[(page-1)*limit:page*limit]:
            if package in top_packages:
                continue
            ret.append({
                'name': package.name,
                'summary': package.description,
                'description': package.long_description,
                'stars': package.stars,
                'download_times': package.download_times,
                'package_type': package.package_type,
                'versions': package.versions,
                'upload_date': package.upload_date
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
        
        pypi_root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        if not os.path.exists(pypi_root):
            os.mkdir(pypi_root)

        query = {'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        else:
            query['organization'] = None
            query['team'] = None

        for name, file in request.files.items():
            if not is_path_secure(file.filename):
                return response_message(EINVAL, 'Illegal file name'), 401
            found = True
            with tempfile.TemporaryDirectory() as tempDir:
                filename = str(Path(tempDir) / file.filename)
                file.save(filename)

                with zipfile.ZipFile(filename) as zf:
                    for f in zf.namelist():
                        if (f.endswith('.md') or f.endswith('.robot')) and not SCRIPT_FILES_FIND(f):
                            return response_message(EINVAL, 'All test scripts should be put in the scripts directory'), 401

                name, description, long_description = get_package_info(filename)
                if not name:
                    return response_message(EINVAL, 'Package name not found'), 401

                package = Package.objects(name=name, **query).first()
                if not package:
                    package = Package(name=name, **query)

                if proprietary:
                    package.organization = organization
                    package.team = team
                try:
                    os.mkdir(pypi_root / package.package_name)
                except FileExistsError:
                    pass
                package.py_packages = get_internal_packages(filename)
                shutil.move(filename, pypi_root / package.package_name / file.filename)
                package.uploader = user
                package.upload_date = datetime.datetime.utcnow
                package.description = description
                package.long_description = long_description
                if file.filename not in package.files:
                    package.files.append(file.filename)
                    package.files.sort(key=lambda x: parse_version(package.version_re(x).group('ver')), reverse=True)
                package.save()

        if not found:
            return response_message(EINVAL, 'File not found'), 404

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('delete the package')
    @api.expect(_delete_package)
    def delete(self, **kwargs):
        """Delete the package"""
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        version = data.get('version', None)
        if not version:
            return response_message(EINVAL, 'Field version is required'), 400
        package_name = data.get('name', None)
        if not package_name:
            return response_message(EINVAL, 'Field name is required'), 400
        
        pypi_root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)

        query = {'name': package_name, 'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        else:
            query['organization'] = None
            query['team'] = None
        
        package = Package.objects(**query).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404
        pkg_file = package.get_package_by_version(version)
        if not pkg_file:
            return response_message(ENOENT, f'Package for version {version} not found'), 404

        try:
            os.unlink(pypi_root / package.package_name / pkg_file)
        except FileNotFoundError:
            pass

        package.modify(pull__files=pkg_file)
        if len(package.files) == 0:
            try:
                shutil.rmtree(pypi_root / package.package_name)
            except FileNotFoundError:
                pass
            package.delete()

        return response_message(SUCCESS)

@api.route('/package')
class PackageInfo(Resource):
    @token_required_if_proprietary
    @api.doc('return the package description of a specified version')
    def get(self, **kwargs):
        data = request.args
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)

        proprietary = js2python_bool(data.get('proprietary', False))
        package_name = data.get('name', None)
        if not package_name:
            return response_message(EINVAL, 'Field name is required'), 400
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        version = data.get('version', None)
        if not version:
            return response_message(EINVAL, 'Field version is required'), 400
        
        pypi_root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        package = Package.objects(proprietary=proprietary, package_type=package_type, name=package_name).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404
        package_path = pypi_root / package.package_name / package.get_package_by_version(version)
        _, _, description = get_package_info(package_path)
        return response_message(SUCCESS, description=description)

    @token_required_if_proprietary
    @api.doc('update the package')
    @api.expect(_upload_package)
    def patch(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        stars = data.get('stars', None)
        if not stars:
            return response_message(EINVAL, 'Field stars is required'), 400
        package_name = data.get('name', None)
        if not package_name:
            return response_message(EINVAL, 'Field name is required'), 400
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        
        query = {'proprietary': proprietary, 'package_type': package_type, 'name': package_name}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        else:
            query['organization'] = None
            query['team'] = None

        package = Package.objects(**query).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404

        rating_times = package.rating_times + 1
        rating = package.rating_times / rating_times * package.rating + 1 / rating_times * stars
        package.modify(rating=rating)
        package.modify(rating_times=rating_times)

        return response_message(SUCCESS, stars=package.stars)

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
        package_name = data.get('name', None)
        if not package_name:
            return response_message(EINVAL, 'Field name is required'), 400
        version = data.get('version', None)
        if not version:
            return response_message(EINVAL, 'Field version is required'), 400
        
        pypi_root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)

        query = {'proprietary': proprietary, 'package_type': package_type, 'name': package_name}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        else:
            query['organization'] = None
            query['team'] = None

        package = Package.objects(**query).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404

        if package_type == 'Test Suite':
            ret = install_test_suite(package, user, organization, team, pypi_root, proprietary, version=version)
            if not ret:
                return response_message(EPERM, 'Test package installation failed'), 400
            package.modify(modified=False)

        return response_message(SUCCESS)

    @token_required
    @organization_team_required_by_json
    @api.doc('uninstall the package')
    @api.expect(_delete_package)
    def delete(self, **kwargs):
        """Uninstall the package"""
        organization = kwargs['organization']
        team = kwargs['team']
        user = kwargs['user']

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return response_message(EINVAL, 'Field package_type is required'), 400
        version = data.get('version', None)
        if not version:
            return response_message(EINVAL, 'Field version is required'), 400
        package_name = data.get('name', None)
        if not package_name:
            return response_message(EINVAL, 'Field name is required'), 400

        query = {'name': package_name, 'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        else:
            query['organization'] = None
            query['team'] = None

        package = Package.objects(**query).first()
        if not package:
            return response_message(ENOENT, 'Package not found'), 404

        scripts_root = get_user_scripts_root(organization=organization, team=team)
        libraries_root = get_back_scripts_root(organization=organization, team=team)
        pypi_root = get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        package_path = pypi_root / package.package_name / package.get_package_by_version(version)
        pkg_names = get_internal_packages(package_path)
        for pkg_name in pkg_names:
            if os.path.exists(scripts_root / pkg_name):
                shutil.rmtree(scripts_root / pkg_name)
            if os.path.exists(libraries_root / pkg_name):
                shutil.rmtree(libraries_root / pkg_name)
        for pkg_name in pkg_names:
            for script in os.listdir(scripts_root / pkg_name):
                test = Test.objects(test_suite=os.path.splitext(script)[0], path=pkg_name).first()
                if test:
                    test.modify(staled=True)
                else:
                    current_app.logger.error(f'test not found for {script}')

        return response_message(SUCCESS)
