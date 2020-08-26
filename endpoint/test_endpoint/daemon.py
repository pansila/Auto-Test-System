import asyncio
import os
import shutil
import sys
import tarfile
import time
import zipfile
from contextlib import contextmanager
from io import BytesIO
from queue import Empty

import requests
from bson.objectid import ObjectId

from .venv_run import empty_folder
from .main import start_remote_server


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
        self._unpack()

        self._create_test_result(test_case)
        server, queue = start_remote_server(backing_file, self.config, task_id=self.task_id)
        self.running_test = server

        # time.sleep(3)
        try:
            ret = queue.get(timeout=5)
        except Empty:
            raise AssertionError("RPC server can't be ready")

    def stop_test(self, test_case, status):
        if self.running_test:
            self._update_test_result(status)
            self.running_test.terminate()
            self.running_test = None
            self.task_id = None

    def _download_file(self, endpoint, dest_dir):
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
        temp.close()

    def _download(self, backing_file, task_id):
        self._download_file(f'test/script?id={task_id}&test={backing_file}', self.config["download_dir"])
        if task_id:
            ObjectId(task_id)  # validate the task id
            test_data_path = os.path.join(self.config["resource_dir"], "test_data")
            self._download_file('taskresource/{}'.format(task_id), test_data_path)

    def _unpack(self):
        packages_data_path = os.path.join(self.config["resource_dir"], 'package_data')
        empty_folder(packages_data_path)
        for pkg_file in os.listdir(self.config["download_dir"]):
            if not pkg_file.endswith('.egg'):
                raise AssertionError("Find an unsupported file: {}".format(f))
            with zipfile.ZipFile(os.path.join(self.config["download_dir"], pkg_file)) as zf:
                packages = (f.split('/', 1)[0] for f in zf.namelist() if not f.startswith('EGG-INFO'))
                packages = set(packages)
                for pkg in packages:
                    resources = [f for f in zf.namelist() if f.startswith(pkg + '/data/')]
                    for r in resources:
                        zf.extract(r, packages_data_path)

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
