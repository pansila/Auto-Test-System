import argparse
import importlib
import multiprocessing
import os.path
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
from distutils import dir_util
from multiprocessing import Queue
from pathlib import Path

from bson.objectid import ObjectId

import requests
from robotremoteserver import RobotRemoteServer
from ruamel import yaml

#from robotlibcore import HybridCore

DOWNLOAD_LIB = "testlibs"
TEMP_LIB = "files"
TERMINATE = 1

g_config = {}

class daemon(object):

    def __init__(self, config):
        self.tests = {}
        self.config = config

        if os.path.exists(self.config["test_dir"]):
            dir_util.remove_tree(self.config["test_dir"])
        os.makedirs(self.config["test_dir"])

        sys.path.insert(0, os.path.realpath(self.config["test_dir"]))

        if os.path.exists(self.config["resource_dir"]):
            dir_util.remove_tree(self.config["resource_dir"])
        os.makedirs(self.config["resource_dir"])

    def start_test(self, testcase, task_id=None):
        if testcase.endswith(".py"):
            testcase = testcase[0:-3]

        self._download(testcase, task_id)
        self._verify(testcase)

        server_queue, server_process = start_remote_server(testcase,
                                    self.config,
                                    host=self.config["host_daemon"],
                                    port=self.config["port_test"])
        self.tests[testcase] = {"queue": server_queue, "process": server_process}
        return

    def stop_test(self, testcase):
        if testcase in self.tests:
            self.tests[testcase]["queue"].put(TERMINATE)
            del self.tests[testcase]["queue"]
            del self.tests[testcase]
            time.sleep(0.5)
        # else:
        #     print("test {} is not running".format(testcase))

    def _download_file(self, endpoint, download_dir):
        tarball = 'download.tar.gz'
        url = "{}:{}/{}".format(self.config["server_url"], self.config["server_port"], endpoint)
        print('Start to download file {} from {}'.format(tarball, url))

        r = requests.get(url)
        if r.status_code == 404:
            raise AssertionError('Downloading file {} failed'.format(tarball))

        output = Path(download_dir) / tarball
        with open(output, 'wb') as f:
            f.write(r.content)
        print('Downloading test file {} succeeded'.format(tarball))

        with tarfile.open(output) as tarFile:
            tarFile.extractall(download_dir)

        temp_dir = Path(download_dir) / TEMP_LIB
        dir_util.copy_tree(temp_dir, download_dir)
        shutil.rmtree(temp_dir)

    def _download(self, testcase, task_id):
        if testcase.endswith(".py"):
            testcase = testcase[0:-3]

        self._download_file('script/{}'.format(testcase), self.config["test_dir"])
        if task_id is not None or task_id != "":
                ObjectId(task_id)  # validate the task id
                self._download_file('taskresource/{}'.format(task_id), self.config["resource_dir"])

    def _verify(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        testlib = Path(self.config["test_dir"]) / testcase
        if not os.path.exists(testlib):
            raise AssertionError("Verifying downloaded file %s failed" % testcase)

    def start(self):
        """ start the daemon """
        pass

    def stop(self):
        """ stop the daemon """
        pass

    def clear_log(self):
        pass

    def upload_log(self):
        pass

# Don't run RobotRemoteServer directly as there is a thread.lock pickling issue
def start_test_library(queue, testcase, config, host, port):
    # importlib.invalidate_caches()
    testlib = importlib.import_module(testcase)
    # importlib.reload(testlib)
    test = getattr(testlib, testcase)

    server = RobotRemoteServer(test(config), host=host, serve=False, port=port)
    server_thread = threading.Thread(target=server.serve)
    server_thread.daemon = True
    server_thread.start()

    while True:
        try:
            item = queue.get()
        except KeyboardInterrupt:
            server._server.shutdown()
            break
        else:
            if item == TERMINATE:
                server._server.shutdown()
                break

    while server_thread.is_alive():
        server_thread.join(0.1)

def start_remote_server(testcase, config, host, port=8270):
    q = Queue()
    server_process = multiprocessing.Process(target=start_test_library, args=(q, testcase, config, host, port))
    server_process.start()
    return q, server_process

def start_daemon(config_file = "config.yml", host=None, port=None):
    global g_config
    with open(config_file, 'r', encoding='utf-8') as f:
        g_config = yaml.load(f, Loader=yaml.RoundTripLoader)

    if host:
        g_config["host_daemon"] = host
    elif "host_daemon" not in g_config:
        g_config["host_daemon"] = '127.0.0.1'

    if port:
        g_config["port_daemon"] = port
        g_config["port_test"] = port + 1
    else:
        if "port_daemon" not in g_config:
            g_config["port_daemon"] = 8270
        if "port_test" not in g_config:
            g_config["port_test"] = 8271

    if "test_dir" not in g_config:
        g_config["test_dir"] = DOWNLOAD_LIB
    if "server_url" not in g_config:
        raise AssertionError('server is not set in the config file')
    else:
        if not g_config['server_url'].startswith('http://'):
            g_config['server_url'] += 'http://'
        if g_config['server_url'][-1] == '/':
            g_config['server_url'] = g_config['server_url'][0:-1]

    server_queue, server_process = start_remote_server('daemon', g_config, host=g_config["host_daemon"], port=g_config["port_daemon"])
    while server_process.is_alive():
        try:
            server_process.join(1)
        except KeyboardInterrupt:
            break

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str,
                        help='the network interface for daemon to listen',
                        default='127.0.0.1')
    parser.add_argument('--port', type=int,
                        help='the port for daemon to listen, the test port will be next it',
                        default=8270)
    args = parser.parse_args()

    host, port = args.host, args.port

    try:
        start_daemon(host=host, port=port)
    except OSError as err:
        print(err)
        print("Please check IP {} is configured correctly".format(g_config["host_daemon"]))
