import json
from datetime import date, datetime

import requests


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

class rest_api():
    def __init__(self, config, task_id):
        self.config = config
        self.task_id = task_id
        self.result = {}
        self._update_result()

    def _update_result(self, new_result=None):
        if new_result:
            self.result = {**self.result, **new_result}
        ret = requests.post('{}/testresult/{}'.format(self.config['server_url'],
                            self.task_id),
                            json=json.dumps(self.result, default=json_serial))
        if ret.status_code != 200:
            raise AssertionError('Updating the results to server failed')
