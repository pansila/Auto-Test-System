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

import aiohttp
from bson.objectid import ObjectId

from .venv_run import empty_folder
from .main import start_remote_server


class daemon(object):

    def __init__(self, config, task_id):
        self.running_tests = {}
        self.config = config
        # only used by test libraries
        # self.task_id = task_id

    async def start_test(self, test_case, task_id=None):
        # used by daemon
        self.task_id = task_id
        ObjectId(task_id)  # validate the task id
        await self._create_test_result(test_case)
        await self._download_package_files()

    async def load_library(self, backing_file):
        # Usually a test is stopped when it ends, stop it here in case a test was aborted or crashed
        await self.stop_test(backing_file, 'FLUSHED')

        if not backing_file.endswith(".py"):
            backing_file += '.py'

        await self._download_standalone_files(backing_file)

        server = start_remote_server(backing_file, self.config, task_id=self.task_id)
        self.running_tests[backing_file] = server

        try:
            ret = server.queue.get(timeout=10)
        except Empty:
            raise AssertionError("RPC server can't be ready")

    async def stop_test(self, backing_file, status):
        if backing_file in self.running_tests:
            print('Stop the RPC server for test')
            await self._update_test_result(status)
            self.running_tests[backing_file].process.terminate()
            del self.running_tests[backing_file]

    def get_endpoint_config(self):
        return self.config

    async def _download_file(self, endpoint, dest_dir):
        url = "{}/{}".format(self.config["server_url"], endpoint)
        print('Start to download file from {}'.format(url))

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 204:
                    print('No files need to download')
                    return

                if response.status != 201:
                    if response.status == 200:
                        print(response)
                        message = response.message
                    else:
                        message = ''
                    raise AssertionError('Downloading file failed: ', message)

                temp = BytesIO()
                ret = await response.read()
                temp.write(ret)
                print('Downloading test file succeeded')

                temp.seek(0)
                with tarfile.open(fileobj=temp) as tarFile:
                    tarFile.extractall(dest_dir)
                temp.close()
                print('Extracting test file succeeded')

    async def _download_package_files(self):
        empty_folder(self.config["download_dir"])
        empty_folder(self.config["resource_dir"])

        await self._download_file(f'api_v1/test/script?id={self.task_id}', self.config["download_dir"])

        test_data_path = os.path.join(self.config["resource_dir"], "test_data")
        await self._download_file(f'api_v1/taskresource/{self.task_id}', test_data_path)

        self._unpack()

    async def _download_standalone_files(self, backing_file):
        """
        Download test files for standalone test libraries that have not been packed into a test package
        """
        if os.listdir(self.config["download_dir"]):
            # test library files have been downloaded from the package system
            return

        await self._download_file(f'api_v1/test/script?id={self.task_id}&test={backing_file}', self.config["download_dir"])

        test_data_path = os.path.join(self.config["resource_dir"], "test_data")
        await self._download_file(f'api_v1/taskresource/{self.task_id}', test_data_path)

        self._unpack()

    def _unpack(self):
        packages_data_path = os.path.join(self.config["resource_dir"], 'package_data')
        for pkg_file in os.listdir(self.config["download_dir"]):
            if not pkg_file.endswith('.egg'):
                raise AssertionError(f'Find an unsupported file: {pkg_file}')
            with zipfile.ZipFile(os.path.join(self.config["download_dir"], pkg_file)) as zf:
                packages = (f.split('/', 1)[0] for f in zf.namelist() if not f.startswith('EGG-INFO'))
                packages = set(packages)
                for pkg in packages:
                    pkg_dir = os.path.join(packages_data_path, pkg)
                    if os.path.exists(pkg_dir):
                        continue
                    resources = [f for f in zf.namelist() if f.startswith(pkg + '/data/')]
                    for r in resources:
                        zf.extract(r, packages_data_path)

    def clear_log(self):
        pass

    def upload_log(self):
        pass

    async def _update_test_result(self, status):
        if not self.task_id:
            return
        data = {'status': status}
        async with aiohttp.ClientSession() as session:
            async with session.post(f'{self.config["server_url"]}/api_v1/testresult/{self.task_id}', json=data) as response:
                if response.status != 200:
                    print('Updating the task result on the server failed')

    async def _create_test_result(self, test_case):
        if not self.task_id:
            return
        data = {'task_id': self.task_id, 'test_case': test_case}
        async with aiohttp.ClientSession() as session:
            async with session.post(f'{self.config["server_url"]}/api_v1/testresult/', json=data) as response:
                if response.status != 200:
                    print('Creating the task result on the server failed')
