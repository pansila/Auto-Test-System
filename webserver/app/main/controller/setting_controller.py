from ..util.dto import SettingDto
from ..util.response import *
from flask_restx import Resource

api = SettingDto.api

@api.route('/rpc')
class rpc_request(Resource):
    @api.doc('Get RPC settings')
    def get(self):
        """
        Get RPC settings
        """
        return {'port': 5555}






