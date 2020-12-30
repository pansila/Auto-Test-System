import os
from pathlib import Path

from sanic.response import json, file
from sanic_openapi import doc
from sanic import Blueprint
from sanic.views import HTTPMethodView

from ..model.database import Package
from ..util.dto import PypiDto
from ..util.response import response_message, ENOENT, EINVAL
from ..util.decorator import token_required_if_proprietary_by_args
from ..util.get_path import get_test_store_root
from ..util import js2python_bool

api = PypiDto.api

@api.route('/')
class ScriptManagement(Resource):
    @api.doc('return package list')
    @token_required_if_proprietary_by_args
    def get(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))

        query = { 'proprietary': proprietary }
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        packages = await Package.find(query)
        headers = {'Content-Type': 'text/html'}
        return make_response(render_template("pypi.html", items=[pkg.name for pkg in packages] , path=''), 200, headers)

@api.route('/<package_name>')
class ScriptManagement(Resource):
    @api.doc('return package files')
    @token_required_if_proprietary_by_args
    def get(self, package_name, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))

        query = { 'proprietary': proprietary, 'name': package_name }
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, f'Package {package_name} not found'))
        headers = {'Content-Type': 'text/html'}
        return make_response(render_template("pypi.html", items=package.files, path=package.name), 200, headers)

@api.route('/<path:package>')
class ScriptManagement(Resource):
    @api.doc('return package')
    @token_required_if_proprietary_by_args
    def get(self, package, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))

        directory, _, file = package.rpartition('/')
        if not directory or not file:
            return json(response_message(EINVAL))
        directory = directory.replace('-', '_').replace(' ', '_')

        query = { 'proprietary': proprietary, 'files': file }
        if proprietary:
            query['organization'] = organization
            query['team'] = team

        package = await Package.find_one(query)
        if not package:
            return json(response_message(ENOENT, f'Package {file} not found'))

        pypi_root = await get_test_store_root(proprietary=proprietary, team=team, organization=organization)
        return send_from_directory(Path(os.getcwd()) / pypi_root / directory, file)
