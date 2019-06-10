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

import requests
from bson.objectid import ObjectId

# import daemon as Daemon
# from daemoniker import Daemonizer, SignalHandler1
from robotremoteserver import RobotRemoteServer
from ruamel import yaml

DOWNLOAD_LIB = "testlibs"
TEMP_LIB = "files"
TERMINATE = 1

g_config = {}

class task_daemon(object):

    def __init__(self, config, task_id):
        self.tests = {}
        self.config = config

        try:
            os.makedirs(self.config["test_dir"])
        except FileExistsError:
            pass
        try:
            os.makedirs(self.config["resource_dir"])
        except FileExistsError:
            pass

        sys.path.insert(0, os.path.realpath(self.config["test_dir"]))

    def start_test(self, test_case, backing_file, task_id=None):
        if backing_file.endswith(".py"):
            backing_file = backing_file[0:-3]

        self.task_id = task_id
        self._download(backing_file, self.task_id)
        self._verify(backing_file)

        server_queue, server_process = start_remote_server(backing_file,
                                    self.config,
                                    host=self.config["host_daemon"],
                                    port=self.config["port_test"],
                                    task_id=self.task_id)
        self.tests[test_case] = {"queue": server_queue, "process": server_process}
        self._create_test_result(test_case)

    def stop_test(self, test_case, status):
        self._update_test_result(status)
        if test_case in self.tests:
            self.tests[test_case]["queue"].put(TERMINATE)
            del self.tests[test_case]["queue"]
            del self.tests[test_case]
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

        if r.status_code == 406:
            print('No files need to download')
            return

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

        self._download_file('test/script?id={}&test={}'.format(task_id, testcase), self.config["test_dir"])
        if task_id:
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

    def _update_test_result(self, status):
        data = {'status': status}
        ret = requests.post('{}:{}/testresult/{}'.format(self.config['server_url'],
                                                         self.config['server_port'],
                                                         self.task_id),
                            json=data)
        if ret.status_code != 200:
            print('Updating the task result on the server failed')

    def _create_test_result(self, test_case):
        data = {'task_id': self.task_id, 'test_case': test_case}
        ret = requests.post('{}:{}/testresult/'.format(self.config['server_url'],
                                                       self.config['server_port']),
                            json=data)
        if ret.status_code != 200:
            print('Creating the task result on the server failed')

# Don't run RobotRemoteServer directly as there is a thread.lock pickling issue
def start_test_library(queue, backing_file, task_id, config, host, port):
    # importlib.invalidate_caches()
    testlib = importlib.import_module(backing_file)
    # importlib.reload(testlib)
    test = getattr(testlib, backing_file)

    server = RobotRemoteServer(test(config, task_id), host=host, serve=False, port=port)
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

def start_remote_server(backing_file, config, host, port=8270, task_id=None):
    queue = Queue()
    server_process = multiprocessing.Process(target=start_test_library,
                                             args=(queue, backing_file, task_id, config, host, port))
    server_process.start()
    return queue, server_process

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

    server_queue, server_process = start_remote_server('task_daemon', g_config, host=g_config["host_daemon"], port=g_config["port_daemon"])
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

    sys.exit(0)

    if os.name == 'nt':
        with Daemonizer() as (is_setup, daemonizer):
            if is_setup:
                pass
            is_parent, host, port = daemonizer('daemon.pid', host, port, stdout_goto='daemon.log', stderr_goto='daemon.log')
            if not is_parent:
                sighandler = SignalHandler1(pid_file)
                sighandler.start()
        try:
            start_daemon(host=host, port=port)
        except OSError as err:
            print(err)
            print("Please check IP {} is configured correctly".format(g_config["host_daemon"]))
    elif os.name == 'posix':
        with Daemon.DaemonContext():
            try:
                start_daemon(host=host, port=port)
            except OSError as err:
                print(err)
                print("Please check IP {} is configured correctly".format(g_config["host_daemon"]))
    else:
        raise AssertionError(os.name + ' is not supported')
