import aiofiles
import asyncio
import datetime
import os
import re
import distutils.core
from pathlib import Path
from pkg_resources import parse_version

from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file
from sanic_openapi import doc

from ..util import async_move, async_rmtree, async_exists, async_listdir
from ..util.zipfile import ZipFile
from ..util.tempdir import TemporaryDirectory
from ..util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json, organization_team_required_by_form, token_required_if_proprietary_by_args, token_required_if_proprietary_by_json
from ..util.get_path import get_test_store_root, is_path_secure, get_user_scripts_root, get_back_scripts_root
from task_runner.util.dbhelper import get_package_info, install_test_suite, get_internal_packages
from ..config import get_config
from ..model.database import Package, Test, PackageFile
from ..util.dto import StoreDto, json_response
from ..util.response import response_message, ENOENT, EINVAL, SUCCESS, EIO, EPERM
from ..util import js2python_bool

_package_query = StoreDto.package_query
_package_info_query = StoreDto.package_info_query
_package_description = StoreDto.package_description
_upload_package = StoreDto.upload_package
_delete_package = StoreDto.delete_package
_package_list = StoreDto.package_list
_package_star = StoreDto.package_star

SCRIPT_FILES_FIND = re.compile(r'^.*?/scripts/.*$').match

bp = Blueprint('store', url_prefix='/store')

class PackageView(HTTPMethodView):
    @doc.summary('return the package list')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_package_query)
    @doc.produces(_package_list)
    @token_required_if_proprietary_by_args
    async def get(self, request):
        data = request.args
        page = data.get('page', default=1)
        limit = data.get('limit', default=10)
        title = data.get('title', default=None)

        page = int(page)
        limit = int(limit)
        if page <= 0 or limit <= 0:
            return json(response_message(EINVAL, 'Field page and limit should be larger than 1'))

        proprietary = js2python_bool(data.get('proprietary', False)) #TODO: check organization and team
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))

        if title:
            query = {'name': {'$regex': title.replace(" ", "-")}, 'proprietary': proprietary, 'package_type': package_type}
        else:
            query = {'proprietary': proprietary, 'package_type': package_type}

        ret = []
        top_package = await Package.find_one({'name': 'Robot-Test-Utility', 'package_type': package_type, 'proprietary': False})
        if top_package:
            ret.append({
                'name': top_package.name,
                'summary': top_package.description,
                'description': top_package.long_description,
                'stars': top_package.stars,
                'download_times': top_package.download_times,
                'package_type': top_package.package_type,
                'versions': await top_package.versions,
                'upload_date': top_package.upload_date
            })

        async for package in Package.find(query).skip((page - 1) * limit).limit(limit):
            if package == top_package:
                continue
            ret.append({
                'name': package.name,
                'summary': package.description,
                'description': package.long_description,
                'stars': package.stars,
                'download_times': sum([(await pkg_file.fetch()).download_times for pkg_file in package.files]),
                'package_type': package.package_type,
                'versions': await package.versions,
                'upload_date': package.upload_date.timestamp() * 1000
            })
        return json(response_message(SUCCESS, packages=ret, total=await Package.count_documents(query)))

    @doc.summary('upload the package')
    @doc.description('''\
        Note: Files in the form request payload are tuples of file name and file content
        which can't be explicitly listed here. Please check out the form data format on the web.
        Usually browser will take care of it.
    ''')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_upload_package, location="formData", content_type="multipart/form-data")
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_form
    async def post(self, request):
        found = False

        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user

        data = request.form
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        
        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        if not await async_exists(pypi_root):
            await aiofiles.os.mkdir(pypi_root)

        query = {'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization.pk
            query['team'] = team.pk if team else None

        for name, files in request.files.items():
            for file in files:
                if not is_path_secure(file.name):
                    return json(response_message(EINVAL, 'Illegal file name'))
                found = True
                async with TemporaryDirectory() as tempDir:
                    filename = os.path.join(tempDir, file.name)
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(file.body)

                    async with ZipFile(filename) as zf:
                        for f in zf.namelist():
                            if (f.endswith('.md') or f.endswith('.robot')) and not SCRIPT_FILES_FIND(f):
                                return json(response_message(EINVAL, 'All test scripts should be put in the scripts directory'))

                    name, description, long_description = await get_package_info(filename)
                    if not name:
                        return json(response_message(EINVAL, 'Package name not found'))

                    query['name'] = name
                    package = await Package.find_one(query)
                    if not package:
                        package = Package(**query)

                    for pkg_file in package.files:
                        pkg_file = await pkg_file.fetch()
                        if pkg_file.version == package.version_re(file.name).group('ver'):
                            pkg_file.filename = file.name
                            pkg_file.description = description
                            pkg_file.long_description = long_description
                            pkg_file.uploader = user
                            pkg_file.upload_date = datetime.datetime.utcnow()
                            await pkg_file.commit()
                            break
                    else:
                        package_file = PackageFile(name=name,
                                                   filename=file.name,
                                                   description=description,
                                                   long_description=long_description,
                                                   uploader=user,
                                                   upload_date=datetime.datetime.utcnow(),
                                                   version=package.version_re(file.name).group('ver'))
                        await package_file.commit()
                        package.files.append(package_file)
                        await package.sort()

                    # if proprietary: #TODO: ???
                    #     package.organization = organization
                    #     if team:
                    #         package.team = team
                    try:
                        await aiofiles.os.mkdir(pypi_root / package.package_name)
                    except FileExistsError:
                        pass
                    package.py_packages = await get_internal_packages(filename)
                    await async_move(filename, pypi_root / package.package_name / file.name)
                    package.uploader = user
                    package.upload_date = datetime.datetime.utcnow()
                    package.description = description
                    package.long_description = long_description
                    await package.commit()

        if not found:
            return json(response_message(EINVAL, 'File not found'))

        return json(response_message(SUCCESS))

    @doc.summary('delete the package')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_delete_package, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        """Delete the package"""
        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        version = data.get('version', None)
        if not version:
            return json(response_message(EINVAL, 'Field version is required'))
        package_name = data.get('name', None)
        if not package_name:
            return json(response_message(EINVAL, 'Field name is required'))
        
        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)

        query = {'name': package_name, 'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization.pk
            query['team'] = team.pk if team else None
        else:
            query['organization'] = None
            query['team'] = None
        
        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, 'Package not found'))
        pkg_file = await package.get_package_by_version(version)
        if not pkg_file:
            return json(response_message(ENOENT, f'Package for version {version} not found'))

        try:
            await aiofiles.os.remove(pypi_root / package.package_name / pkg_file.filename)
        except FileNotFoundError:
            pass

        package.files.remove(pkg_file)
        await package.commit()
        if len(package.files) == 0:
            try:
                await async_rmtree(pypi_root / package.package_name)
            except FileNotFoundError:
                pass
            await package.delete()
        else:
            latest_pkg_file = await package.get_package_by_version()
            name, description, long_description = await get_package_info(pypi_root / package.package_name / latest_pkg_file.filename)
            if not name:
                return json(response_message(EINVAL, 'Package file {} not found'.format(latest_pkg_file.filename)))

            package.uploader = latest_pkg_file.uploader
            package.upload_date = latest_pkg_file.upload_date
            package.description = latest_pkg_file.description
            package.long_description = latest_pkg_file.long_description
            await package.commit()

        return json(response_message(SUCCESS))

class PackageInfoView(HTTPMethodView):
    @doc.summary('return the package description of a specified version')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_package_info_query)
    @doc.produces(_package_description)
    @token_required_if_proprietary_by_args
    async def get(self, request):
        data = request.args
        proprietary = js2python_bool(data.get('proprietary', False))
        organization, team = None, None
        if proprietary:
            organization = request.ctx.organization
            team = request.ctx.team
        package_name = data.get('name', None)
        if not package_name:
            return json(response_message(EINVAL, 'Field name is required'))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        version = data.get('version', None)
        if not version:
            return json(response_message(EINVAL, 'Field version is required'))
        
        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        package = await Package.find_one({'proprietary': proprietary, 'package_type': package_type, 'name': package_name})
        if not package:
            return json(response_message(ENOENT, 'Package not found'))
        package_path = pypi_root / package.package_name / (await package.get_package_by_version(version)).filename
        _, _, description = await get_package_info(package_path)
        return json(response_message(SUCCESS, description=description))

    @doc.summary('update the package')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_upload_package, location='body')
    @doc.produces(_package_star)
    @token_required_if_proprietary_by_json
    async def patch(self, request):
        organization = request.ctx.organization
        team = request.ctx.team

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        stars = data.get('stars', None)
        if not stars:
            return json(response_message(EINVAL, 'Field stars is required'))
        package_name = data.get('name', None)
        if not package_name:
            return json(response_message(EINVAL, 'Field name is required'))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        
        query = {'proprietary': proprietary, 'package_type': package_type, 'name': package_name}
        if proprietary:
            query['organization'] = organization.pk
            query['team'] = team.pk if team else None
        else:
            query['organization'] = None
            query['team'] = None

        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, 'Package not found'))

        rating_times = package.rating_times + 1
        rating = package.rating_times / rating_times * package.rating + 1 / rating_times * stars
        await package.update({'rating': rating})
        await package.update({'rating_times': rating_times})

        return json(response_message(SUCCESS, stars=package.stars))

    @doc.summary('install the package')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_upload_package, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def put(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        package_name = data.get('name', None)
        if not package_name:
            return json(response_message(EINVAL, 'Field name is required'))
        version = data.get('version', None)
        if not version:
            return json(response_message(EINVAL, 'Field version is required'))
        
        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)

        query = {'proprietary': proprietary, 'package_type': package_type, 'name': package_name}
        if proprietary:
            query['organization'] = organization.pk
            query['team'] = team.pk if team else None
        else:
            query['organization'] = None
            query['team'] = None

        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, 'Package not found'))

        if package_type == 'Test Suite':
            ret = await install_test_suite(package, user, organization, team, pypi_root, proprietary, version=version, installed={})
            if not ret:
                return json(response_message(EPERM, 'Test package installation failed'))
            package.modified = False
            await package.commit()

        return json(response_message(SUCCESS))

    @doc.summary('uninstall the package')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_delete_package, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        """Uninstall the package"""
        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user

        data = request.json
        proprietary = js2python_bool(data.get('proprietary', False))
        package_type = data.get('package_type', None)
        if not package_type:
            return json(response_message(EINVAL, 'Field package_type is required'))
        version = data.get('version', None)
        if not version:
            return json(response_message(EINVAL, 'Field version is required'))
        package_name = data.get('name', None)
        if not package_name:
            return json(response_message(EINVAL, 'Field name is required'))

        query = {'name': package_name, 'proprietary': proprietary, 'package_type': package_type}
        if proprietary:
            query['organization'] = organization.pk
            query['team'] = team.pk if team else None
        else:
            query['organization'] = None
            query['team'] = None

        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, 'Package not found'))

        scripts_root = await get_user_scripts_root(organization=organization, team=team)
        libraries_root = await get_back_scripts_root(organization=organization, team=team)
        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        package_path = pypi_root / package.package_name / (await package.get_package_by_version(version)).filename
        pkg_names = await get_internal_packages(package_path)
        for pkg_name in pkg_names:
            for script in await async_listdir(scripts_root / pkg_name):
                test = await Test.find_one({'test_suite': os.path.splitext(script)[0], 'path': pkg_name, 'organization': organization.pk, 'team': team.pk if team else None})
                if test:
                    await test.delete()
                    # test.staled = True
                    # await test.commit()
                else:
                    logger.error(f'test not found for {script}')
        for pkg_name in pkg_names:
            if await async_exists(scripts_root / pkg_name):
                await async_rmtree(scripts_root / pkg_name)
            if await async_exists(libraries_root / pkg_name):
                await async_rmtree(libraries_root / pkg_name)

        return json(response_message(SUCCESS))

bp.add_route(PackageView.as_view(), '/')
bp.add_route(PackageInfoView.as_view(), '/package')
