import json
from datetime import date, datetime

import requests
from .utilities import test_utility


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

class server_api(test_utility):
    def __init__(self, daemon_config, task_id):
        super().__init__(daemon_config, task_id)
        self.result = {}
        # create an empty record in the database
        self._update_result()

    def _update_result(self, new_result=None):
        if new_result:
            self.result = {**self.result, **new_result}
        ret = requests.post('{}/api_v1/testresult/{}'.format(self.daemon_config['server_url'],
                            self.task_id),
                            json=json.dumps(self.result, default=json_serial))
        if ret.status_code != 200:
            raise AssertionError('Updating the results to server failed')
