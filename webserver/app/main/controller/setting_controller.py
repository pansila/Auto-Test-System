import os
import shutil
from urllib.parse import urlparse
from pathlib import Path
from ..util.dto import SettingDto
from ..util.response import *
from flask import send_from_directory, request, current_app
from flask_restx import Resource

api = SettingDto.api

@api.route('/rpc')
class rpc_request(Resource):
    @api.doc('Get RPC settings')
    def get(self):
        """
        Get RPC settings
        """
        return {'rpc_port': 5555}

@api.route('/download')
class download_request(Resource):
    @api.param('file', description='The file path')
    @api.doc('Get installation packages for the endpooint')
    def get(self, **kwargs):
        """
        Get installation packages for the endpooint
        """
        file = request.args.get('file', default=None)
        if not file:
            return response_message(EINVAL, 'Field file is required'), 400

        ret = urlparse(request.url)
        if file == 'get-endpoint.py' or file == 'get-poetry.py':
            src = os.path.join('static', 'download', 'template.' + file)
            new = os.path.join('static', 'download', file)
            if os.path.exists(new):
                os.unlink(new)
            with open(src) as f_src, open(new, 'w') as f_new:
                for line in f_src:
                    if '{server_url}' in line:
                        server_url = ret.scheme + '://' + ret.netloc.replace('localhost', '127.0.0.1')
                        line = line.format(server_url=server_url)
                    f_new.write(line)
        return send_from_directory(Path(os.getcwd()) / 'static' / 'download', file)

@api.route('/get-endpoint/json')
class download_request(Resource):
    @api.doc('Get package information for the poetry')
    def get(self):
        """
        Get package information for the poetry
        """
        return {'releases': ["0.2.3"]}

@api.route('/get-poetry/json')
class download_request(Resource):
    @api.doc('Get package information for the poetry')
    def get(self):
        """
        Get package information for the poetry
        """
        return {'releases': ["1.1.4"]}
