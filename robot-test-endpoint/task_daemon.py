import argparse
import importlib
import multiprocessing
import os
import os.path
import queue
import shutil
import signal
import subprocess
import sys
import socket
import tarfile
import threading
import time
from contextlib import closing
from io import BytesIO
from multiprocessing import Queue
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import requests
from bson.objectid import ObjectId

# import daemon as Daemon
# from daemoniker import Daemonizer, SignalHandler1
from robotremoteserver import RobotRemoteServer
from ruamel import yaml

DOWNLOAD_LIB = "testlibs"
TERMINATE = 1
TEST_END = 2

g_config = {}

def stop_process(queue, process):
    if not queue or not process:
        return
    queue.put(TERMINATE)
    time.sleep(0.1)
    try:
        ret = queue.get(timeout=5)
    except queue.Empty:
        print('Failed to stop test, try killing it')
        process.terminate()
    else:
        if ret != TEST_END:
            print('Failed to stop process due to wrong return {}, try killing it'.format(ret))
            process.terminate()

def empty_folder(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

class task_daemon(object):

    def __init__(self, config, task_id):
        self.running_test = None
        self.config = config
        self.task_id = None

        try:
            os.makedirs(self.config["test_dir"])
        except FileExistsError:
            pass
        try:
            os.makedirs(self.config["resource_dir"])
        except FileExistsError:
            pass

        sys.path.insert(0, os.path.realpath(self.config["test_dir"]))

    def __check_port(self):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(2)
            result = sock.connect_ex((self.config["host_daemon"], self.config["port_test"]))
            if result == 0:
                return False
            else:  # 10061 ususally
                return True
        return True

    def start_test(self, test_case, backing_file, task_id=None):
        # Usually a test is stopped when it ends, need to clean up the remaining server if a test was cancelled or crashed
        self.stop_test('', 'ABORT')

        if backing_file.endswith(".py"):
            backing_file = backing_file[0:-3]

        self.task_id = task_id
        self._download(backing_file, self.task_id)
        self._verify(backing_file)

        if not self.__check_port():
            raise AssertionError('Port is used')

        self._create_test_result(test_case)
        server_queue, server_process = start_remote_server(backing_file,
                                    self.config,
                                    host=self.config["host_daemon"],
                                    port=self.config["port_test"],
                                    task_id=self.task_id)
        self.running_test = {"queue": server_queue, "process": server_process}

    def stop_test(self, test_case, status):
        if self.running_test:
            self._update_test_result(status)
            stop_process(self.running_test["queue"], self.running_test["process"])
            self.running_test = None
            self.task_id = None

    def _download_file(self, endpoint, dest_dir):
        empty_folder(dest_dir)

        url = "{}:{}/{}".format(self.config["server_url"], self.config["server_port"], endpoint)
        print('Start to download file from {}'.format(url))

        r = requests.get(url)
        if r.status_code == 404:
            raise AssertionError('Downloading file failed')

        if r.status_code == 406:
            print('No files need to download')
            return

        temp = BytesIO()
        temp.write(r.content)
        print('Downloading test file succeeded')

        temp.seek(0)
        with tarfile.open(fileobj=temp) as tarFile:
            tarFile.extractall(dest_dir)

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
        if not self.task_id:
            return
        data = {'status': status}
        ret = requests.post('{}:{}/testresult/{}'.format(self.config['server_url'],
                                                         self.config['server_port'],
                                                         self.task_id),
                            json=data)
        if ret.status_code != 200:
            print('Updating the task result on the server failed')

    def _create_test_result(self, test_case):
        if not self.task_id:
            return
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
    timeout = 0

    server = RobotRemoteServer(test(config, task_id), host=host, serve=False, port=port)
    server_thread = threading.Thread(target=server.serve)
    server_thread.daemon = True
    server_thread.start()

    while True:
        try:
            item = queue.get()
        except KeyboardInterrupt:
            server.stop()
            break
        else:
            if item == TERMINATE:
                server.stop()
                break

    while server_thread.is_alive():
        server_thread.join(0.1)
        timeout = timeout + 0.1
        if timeout > 2:
            # force to break if some keyword runs too long blocking the terminate request
            break

    queue.put(TEST_END)

def start_remote_server(backing_file, config, host, port=8270, task_id=None):
    queue = Queue()
    server_process = multiprocessing.Process(target=start_test_library, name='test_library',
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
    return server_queue, server_process

class Config_Handler(FileSystemEventHandler):
    def __init__(self, queue, process, host, port):
        self.queue = queue
        self.process = process
        self.host = host
        self.port = port

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("config.yml"):
            stop_process(self.queue, self.process)
            self.queue, self.process = start_daemon(host=self.host, port=self.port)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str,
                        help='the network interface for daemon to listen',
                        default='0.0.0.0')
    parser.add_argument('--port', type=int,
                        help='the port for daemon to listen, the test port will be next it',
                        default=8270)
    args = parser.parse_args()

    try:
        queue, process = start_daemon(host=args.host, port=args.port)
    except OSError as err:
        print(err)
        print("Please ensure IP {} is configured correctly".format(g_config["host_daemon"]))
        sys.exit(1)

    handler = Config_Handler(queue, process, args.host, args.port)
    ob = Observer()
    watch = ob.schedule(handler, path='.')
    ob.start()

    while ob.is_alive():
        try:
            ob.join(1)
        except KeyboardInterrupt:
            ob.stop()
            break

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
