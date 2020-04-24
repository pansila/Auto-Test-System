import os
import sys
import shutil
import tarfile
import time
from io import BytesIO
from contextlib import contextmanager

import requests
from bson.objectid import ObjectId

from .daemon import start_remote_server


def empty_folder(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

class daemon(object):

    def __init__(self, config, task_id):
        self.running_test = None
        self.config = config
        self.task_id = None

    def start_test(self, test_case, backing_file, task_id=None):
        # Usually a test is stopped when it ends, need to clean up the remaining server if a test was cancelled or crashed
        self.stop_test('', 'ABORT')

        if not backing_file.endswith(".py"):
            backing_file += '.py'

        self.task_id = task_id
        self._download(backing_file, self.task_id)
        self._verify(backing_file)

        self._create_test_result(test_case)
        server = start_remote_server(backing_file,
                                    self.config,
                                    host=self.config["server_host"],
                                    port=self.config["server_rpc_port"],
                                    task_id=self.task_id
                                    )
        self.running_test = server

        for i in range(5):
            if not server.is_ready():
                time.sleep(1)
            else:
                break
        else:
            raise AssertionError("RPC server can't be ready")

    def stop_test(self, test_case, status):
        if self.running_test:
            self._update_test_result(status)
            self.running_test.stop()
            self.running_test = None
            self.task_id = None

    def _download_file(self, endpoint, dest_dir):
        if not os.path.exists(dest_dir):
            os.mkdir(dest_dir)
        else:
            empty_folder(dest_dir)

        url = "{}/{}".format(self.config["server_url"], endpoint)
        print('Start to download file from {}'.format(url))

        r = requests.get(url)
        if r.status_code == 406:
            print('No files need to download')
            return

        if r.status_code != 200:
            raise AssertionError('Downloading file failed')

        temp = BytesIO()
        temp.write(r.content)
        print('Downloading test file succeeded')

        temp.seek(0)
        with tarfile.open(fileobj=temp) as tarFile:
            tarFile.extractall(dest_dir)

    def _download(self, backing_file, task_id):
        self._download_file(f'test/script?id={task_id}&test={backing_file}', self.config["download_dir"])
        if task_id:
            ObjectId(task_id)  # validate the task id
            self._download_file('taskresource/{}'.format(task_id), self.config["resource_dir"])

    def _verify(self, backing_file):
        found = False
        for f in os.listdir(self.config["download_dir"]):
            if not f.endswith('.egg'):
                raise AssertionError("Verifying downloaded file failed")
            else:
                found = True
        if not found:
            raise AssertionError("No downloaded files found")

    def clear_log(self):
        pass

    def upload_log(self):
        pass

    def _update_test_result(self, status):
        if not self.task_id:
            return
        data = {'status': status}
        ret = requests.post('{}/testresult/{}'.format(self.config['server_url'], self.task_id),
                            json=data)
        if ret.status_code != 200:
            print('Updating the task result on the server failed')

    def _create_test_result(self, test_case):
        if not self.task_id:
            return
        data = {'task_id': self.task_id, 'test_case': test_case}
        ret = requests.post('{}/testresult/'.format(self.config['server_url']),
                            json=data)
        if ret.status_code != 200:
            print('Creating the task result on the server failed')
