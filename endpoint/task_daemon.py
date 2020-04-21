import argparse
import asyncio
import functools
import importlib
import inspect
import json
import os
import os.path
import queue
import shutil
import signal
import socket
import sys
import tarfile
import threading
import time
import traceback
import uuid
from contextlib import closing, contextmanager
from io import BytesIO
from pathlib import Path

import requests
import websockets
from bson.objectid import ObjectId
from robotremoteserver import RobotRemoteServer, RemoteLibraryFactory
from ruamel import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from wsrpc import WebsocketRPC
# import daemon as Daemon
# from daemoniker import Daemonizer, SignalHandler1

DOWNLOAD_LIB = "testlibs"
RESOURCE_DIR = "resources"

__TEST_LIB__ = 'daemon'


class SecureWebsocketRPC(WebsocketRPC):
    def __init__(
        self,
        ws,
        handler_cls=None,
        *,
        client_mode: bool = False,
        timeout=10,
        http_request=None,
        method_prefix: str = "rpc_"
    ):
        if handler_cls and not inspect.isclass(handler_cls):
            handler = handler_cls
        super().__init__(ws, None, client_mode=client_mode, timeout=timeout, http_request=http_request, method_prefix=method_prefix)
        if handler_cls and not inspect.isclass(handler_cls):
            self.handler = handler

class WebsocketRemoteServer(RobotRemoteServer):
    def __init__(self, library):
        self._library = RemoteLibraryFactory(library)

def empty_folder(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

@contextmanager
def install_eggs(egg_path):
    org_path = sys.path
    for f in os.listdir(egg_path):
        egg_path = os.path.join(egg_path, f)
        if egg_path not in sys.path:
            sys.path.append(egg_path)
    yield
    sys.path = org_path

class SignalHandler(object):

    def __init__(self, handler):
        self._handler = lambda signum, frame: handler()
        self._original = {}

    def __enter__(self):
        for name in 'SIGINT', 'SIGTERM', 'SIGHUP':
            if hasattr(signal, name):
                try:
                    orig = signal.signal(getattr(signal, name), self._handler)
                except ValueError:  # Not in main thread
                    return
                self._original[name] = orig

    def __exit__(self, *exc_info):
        while self._original:
            name, handler = self._original.popitem()
            signal.signal(getattr(signal, name), handler)

class daemon(object):

    def __init__(self, config, task_id):
        self.running_test = None
        self.config = config
        self.task_id = None

        # sys.path.insert(0, os.path.realpath(self.config["test_dir"]))

    def start_test(self, test_case, backing_file, task_id=None):
        # Usually a test is stopped when it ends, need to clean up the remaining server if a test was cancelled or crashed
        self.stop_test('', 'ABORT')

        if not backing_file.endswith(".py"):
            backing_file += '.py'

        self.task_id = task_id
        self._download(backing_file, self.task_id)
        self._verify(backing_file)
        self._install_eggs()

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
        self._download_file(f'test/script?id={task_id}&test={backing_file}', self.config["test_dir"])
        if task_id:
            ObjectId(task_id)  # validate the task id
            self._download_file('taskresource/{}'.format(task_id), self.config["resource_dir"])

    def _verify(self, backing_file):
        found = False
        for f in os.listdir(self.config["test_dir"]):
            if not f.endswith('.egg'):
                raise AssertionError("Verifying downloaded file failed")
            else:
                found = True
        if not found:
            raise AssertionError("No downloaded files found")

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

class test_library(threading.Thread):
    def __init__(self, backing_file, task_id, config, host, port, rpc_daemon=False):
        super().__init__()
        self.backing_file = backing_file
        self.task_id = task_id
        self.config = config
        self.host = host
        self.port = port
        self.name = backing_file
        self.websocket = None
        self.loop = None
        self.rpc_daemon = rpc_daemon

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        with install_eggs(self.config['test_dir']):
            self.loop.run_until_complete(self.go())

    def is_ready(self):
        return self.websocket is not None

    async def go(self):
        module_name = os.path.splitext(self.backing_file)[0].replace('/', '.')
        importlib.invalidate_caches()
        test_module = importlib.import_module(module_name)
        test_module = importlib.reload(test_module)
        items = []
        for name, value in inspect.getmembers(test_module):
            if inspect.isclass(value) and str(value).split('\'')[1].startswith(module_name):
                items.append(value)
        if len(items) == 1:
            test_lib = items[0]
        elif len(items) > 1:
            test_lib_name = getattr(test_module, '__TEST_LIB__', None)
            if not test_lib_name:
                print('More than one class is defined but "__TEST_LIB__" not defined')
                return
            test_lib = getattr(test_module, test_lib_name, None)
            if not test_lib:
                print(f'Could not find the test library {test_lib_name} in the module {module_name}')
                return
        else:
            print(f'Could not find any test library in the module {module_name}')
            return

        while True:
            try:
                async with websockets.connect(f'ws://{self.host}:{self.port}/') as ws:
                    await ws.send(json.dumps({'organization_id': self.config['organization_id'],
                                   'uid': self.config['uuid'],
                                   'backing_file': self.backing_file if not self.rpc_daemon else ''
                                   }))
                    try:
                        await ws.recv()
                    except websockets.exceptions.ConnectionClosedOK:
                        await asyncio.sleep(10)
                        continue
                    self.websocket = ws
                    print(f'Start RPC server - {threading.current_thread().name}')
                    try:
                        await SecureWebsocketRPC(ws, WebsocketRemoteServer(test_lib(self.config, self.task_id)), method_prefix='').run()
                    except websockets.exceptions.ConnectionClosedError:
                        print('Websocket closed')
            except ConnectionRefusedError:
                print('Network connection is not ready')
            if not self.rpc_daemon:
                print(f'Exit RPC server - {threading.current_thread().name}')
                break
            print(f'Restart due to network connection closed - {threading.current_thread().name}')

    async def stop_websocket(self):
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    def stop(self):
        fut = asyncio.run_coroutine_threadsafe(self.stop_websocket(), self.loop)
        try:
            fut.result()
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            print(exc_type, exc_value)
            traceback.print_tb(exc_tb)
        finally:
            self.loop.stop()

def start_remote_server(backing_file, config, host='127.0.0.1', port=5555, task_id=None, rpc_daemon=False):
    thread = test_library(backing_file, task_id, config, host, port, rpc_daemon)
    thread.start()
    return thread

def get_rpc_port(url):
    ret = requests.get(f'{url}/setting/rpc')
    if ret.status_code != 200:
        print('Failed to get the server RPC port')
        return None
    if 'port' not in ret.json():
        return None
    return ret.json()['port']

def read_config(config_file = "config.yml", host=None, port=None):
    build_uuid = False
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.RoundTripLoader)

    if 'organization_id' not in config or not config['organization_id']:
        print('organization ID must be specified before connecting, you can find it on the user profile page on the server')
        sys.exit(1)

    if 'uuid' not in config or not config['uuid']:
        build_uuid = True
    else:
        try:
            uuid.UUID(config['uuid'])
        except Exception:
            build_uuid = True
    if build_uuid:
        config['uuid'] = str(uuid.uuid1())
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, Dumper=yaml.RoundTripDumper)
        print(f"Generating endpoint's UUID {config['uuid']}")
        print("Please authorize it on the server's endpoint page to activate it")

    if host:
        config["server_host"] = host
    elif "host" not in config:
        config["server_host"] = '127.0.0.1'

    if port:
        config["server_port"] = port
    elif "port" not in config:
        config["server_port"] = 5000

    if "test_dir" not in config:
        config["test_dir"] = DOWNLOAD_LIB
    try:
        os.makedirs(config["test_dir"])
    except FileExistsError:
        pass
    if "resource_dir" not in config:
        config["resource_dir"] = RESOURCE_DIR
    try:
        os.makedirs(config["resource_dir"])
    except FileExistsError:
        pass

    config['server_url'] = 'http://{}:{}'.format(config['server_ip'], config['server_port'])
    try:
        rpc_port = get_rpc_port(config['server_url'])
    except requests.exceptions.ConnectionError:
        config['server_rpc_port'] = 5555
    else:
        if rpc_port:
            config['server_rpc_port'] = rpc_port
        else:
            config['server_rpc_port'] = 5555

    return config

def start_daemon(config, host, port):
    server = start_remote_server(__file__, config, host=config['server_host'], port=config['server_rpc_port'], rpc_daemon=True)
    return server

class Config_Handler(FileSystemEventHandler):
    def __init__(self):
        self.restart = True

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("config.yml"):
            self.restart = True

def run(config_watchdog, handler, host, port):
    daemon = None
    while config_watchdog.is_alive():
        if handler.restart:
            if daemon:
                daemon.stop()
            config = read_config(host=host, port=port)
            daemon = start_daemon(config, host, port)
            handler.restart = False

        try:
            daemon.join(1)
        except KeyboardInterrupt:
            config_watchdog.stop()
            daemon.stop()
            break

        if not daemon.is_alive():
            config_watchdog.stop()
            break
    else:
        daemon.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str,
                        help='the server IP for daemon to connect',
                        default='127.0.0.1')
    parser.add_argument('--port', type=int,
                        help='the server port for daemon to connect',
                        default=5000)
    args = parser.parse_args()
    host, port = args.host, args.port

    handler = Config_Handler()
    ob = Observer()
    watch = ob.schedule(handler, path='.')
    ob.start()

    run(ob, handler, host, port)

    sys.exit(0)

    """
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
            print("Please check IP {} is configured correctly")
    elif os.name == 'posix':
        with Daemon.DaemonContext():
            try:
                start_daemon(host=host, port=port)
            except OSError as err:
                print(err)
                print("Please check IP {} is configured correctly")
    else:
        raise AssertionError(os.name + ' is not supported')
    """
