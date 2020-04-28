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
        return {'rpc_port': 5555, 'msg_port': 5556}


@api.route('/get-endpoint/<file>')
class download_request(Resource):
    @api.doc('Get application for the endpooint')
    def get(self, file):
        """
        Get application for the endpooint
        """
        return send_from_directory(Path(os.getcwd()) / 'static' / 'download', file)
