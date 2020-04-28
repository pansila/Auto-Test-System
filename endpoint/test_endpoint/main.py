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
import time
import traceback
import uuid
import subprocess
import site
from contextlib import closing, contextmanager
from io import BytesIO
from pathlib import Path
from copy import copy
from multiprocessing import Process, Queue

import requests
import websockets
from bson.objectid import ObjectId
# from robotremoteserver import RobotRemoteServer, RemoteLibraryFactory
from .async_remote_library import AsyncRemoteLibrary
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from wsrpc import WebsocketRPC
import toml
# import daemon as Daemon
# from daemoniker import Daemonizer, SignalHandler1


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

@contextmanager
def install_eggs(egg_path):
    org_path = sys.path
    eggs = [os.path.join(egg_path, f) for f in os.listdir(egg_path) if f.endswith('.egg')]
    sys.path[:0] = eggs
    yield
    sys.path = org_path

@contextmanager
def pushd(new_path):
    old_path = os.getcwd()
    os.chdir(new_path)
    yield
    os.chdir(old_path)

@contextmanager
def activate_venv(venv):
    old_os_path = os.environ.get('PATH', '')
    if sys.platform == 'win32':
        os.environ['PATH'] = os.path.dirname(os.path.join(venv, 'Scripts')) + os.pathsep + old_os_path
        site_packages = os.path.join(venv, 'Lib', 'site-packages')
    else:
        os.environ['PATH'] = os.path.dirname(os.path.join(venv, 'bin')) + os.pathsep + old_os_path
        site_packages = os.path.join(venv, 'lib', 'python%s' % sys.version[:3], 'site-packages')
    prev_sys_path = list(sys.path)
    site.addsitedir(site_packages)
    sys.real_prefix = sys.prefix
    sys.prefix = venv
    # Move the added items to the front of the path:
    new_sys_path = []
    for item in list(sys.path):
        if item not in prev_sys_path:
            new_sys_path.append(item)
            sys.path.remove(item)
    sys.path[:0] = new_sys_path
    yield
    os.environ['PATH'] = old_os_path
    sys.path = prev_sys_path

@contextmanager
def activate_workspace(workspace):
    if not os.path.exists(os.path.join(workspace, 'pyproject.toml')):
        raise RuntimeError('workspace\'s configuration file pyproject.toml not found')
    with pushd(workspace):
        try:
            env = copy(dict(os.environ))
            # workaround, otherwise we get the wrong result as we are already in a virtual environment
            del env['VIRTUAL_ENV']
            venv = subprocess.check_output('poetry env info --path', shell=True, text=True, env=env)
        except subprocess.CalledProcessError as e:
            raise AssertionError(f'Failed to get the virtual environment path, please ensure that poetry is in the PATH and virtualenv for workspace has been created')
        with activate_venv(venv):
            yield

class test_library_rpc(Process):
    def __init__(self, backing_file, task_id, config, queue, rpc_daemon=False):
        super().__init__()
        self.backing_file = backing_file
        self.task_id = task_id
        self.config = config
        self.host = config['server_host']
        self.rpc_port = config['server_rpc_port']
        self.msg_port = config['server_msg_port']
        self.name = backing_file
        self.websocket = None
        self.loop = None
        self.rpc_daemon = rpc_daemon
        self.queue = queue

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        if not self.rpc_daemon:
            with activate_workspace('workspace'):
                with install_eggs(self.config['download_dir']):
                    task = asyncio.ensure_future(self.go())
                    task.add_done_callback(self.task_done_check)
                    self.loop.run_until_complete(task)
        else:
            task = asyncio.ensure_future(self.go())
            task.add_done_callback(self.task_done_check)
            self.loop.run_until_complete(task)

    def task_done_check(self, fut):
        try:
            fut.result()
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            print(exc_type, exc_value)
            traceback.print_tb(exc_tb)

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
                async with websockets.connect(f'ws://{self.host}:{self.rpc_port}/') as rpc_ws, websockets.connect(f'ws://{self.host}:{self.msg_port}/') as msg_ws:
                    await rpc_ws.send(json.dumps({'join_id': self.config['join_id'],
                                   'uid': self.config['uuid'],
                                   'backing_file': self.backing_file if not self.rpc_daemon else ''
                                   }))
                    try:
                        await rpc_ws.recv()
                    except websockets.exceptions.ConnectionClosedOK:
                        await asyncio.sleep(10)
                        continue
                    self.queue.put(1)
                    print('Start the RPC server')
                    try:
                        await SecureWebsocketRPC(rpc_ws, AsyncRemoteLibrary(test_lib(self.config, self.task_id), (msg_ws, self.task_id)), method_prefix='').run()
                    except websockets.exceptions.ConnectionClosedError:
                        print('Websocket closed')
            except ConnectionRefusedError:
                pass
                # print('Network connection is not ready')
            if not self.rpc_daemon:
                print('Exit RPC server')
                break
            # print('Restart due to network connection closed')
            await asyncio.sleep(1)

def start_remote_server(backing_file, config, task_id=None, rpc_daemon=False):
    queue = Queue()
    process = test_library_rpc(backing_file, task_id, config, queue, rpc_daemon)
    process.start()
    return process, queue

def get_websocket_ports(url):
    ret = requests.get(f'{url}/setting/rpc')
    if ret.status_code != 200:
        print('Failed to get the server RPC port')
        return None
    ret = ret.json()
    if 'rpc_port' not in ret or 'msg_port' not in ret:
        return None
    return ret['rpc_port'], ret['msg_port']

def read_toml_config(config_file = "pyproject.toml", host=None, port=None):
    toml_config = toml.load(config_file)
    if 'join_id' not in toml_config['tool']['robotest']['settings'] or not toml_config['tool']['robotest']['settings']['join_id']:
        print("'join_id' must be specified in the pyproject.toml, it's either organization's id or team's id you want to join.")
        print("You can find it on the server's global settings sidebar")
        return None

    build_uuid = False
    if 'uuid' not in toml_config['tool']['robotest']['settings'] or not toml_config['tool']['robotest']['settings']['uuid']:
        build_uuid = True
    else:
        try:
            uuid.UUID(toml_config['tool']['robotest']['settings']['uuid'])
        except Exception:
            build_uuid = True
    if build_uuid:
        toml_config['tool']['robotest']['settings']['uuid'] = str(uuid.uuid1())
        with open(config_file, 'w') as fp:
            toml.dump(toml_config, fp)

    config = {
        **toml_config['tool']['robotest']['settings'],
        'download_dir': os.path.abspath(os.path.join('workspace', 'downloads')),
        'resource_dir': os.path.abspath(os.path.join('workspace', 'resources')),
    }
    if host:
        config["server_host"] = host
    elif not config["server_host"]:
        config["server_host"] = '127.0.0.1'
    if port:
        config["server_port"] = port
    elif not config["server_port"]:
        config["server_port"] = 5000

    config['server_url'] = 'http://{}:{}'.format(config['server_host'], config['server_port'])
    try:
        rpc_port, msg_port = get_websocket_ports(config['server_url'])
    except requests.exceptions.ConnectionError:
        config['server_rpc_port'] = 5555
        config['server_msg_port'] = 5556
    else:
        if rpc_port:
            config['server_rpc_port'] = rpc_port
            config['server_msg_port'] = msg_port
        else:
            config['server_rpc_port'] = 5555
            config['server_msg_port'] = 5556
    return config

def start_daemon(config):
    return start_remote_server('test_endpoint/daemon.py', config, rpc_daemon=True)

class Config_Handler(FileSystemEventHandler):
    def __init__(self):
        self.restart = True

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("pyproject.toml"):
            self.restart = True

async def watchdog_run(config_watchdog, handler, host, port):
    daemon = None
    queue = None
    while config_watchdog.is_alive():
        if handler.restart:
            if daemon:
                await daemon.terminate()
            config = read_toml_config(host=host, port=port)
            if not config:
                config_watchdog.stop()
                break
            # config = read_config(host=host, port=port)
            daemon, _ = start_daemon(config)
            handler.restart = False

        try:
            daemon.join(1)
        except KeyboardInterrupt:
            config_watchdog.stop()
            await daemon.terminate()
            break

        if not daemon.is_alive():
            config_watchdog.stop()
            break
    else:
        await daemon.terminate()

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str,
                        help='the server IP for daemon to connect')
    parser.add_argument('--port', type=int,
                        help='the server port for daemon to connect')
    args = parser.parse_args()
    host, port = args.host, args.port

    handler = Config_Handler()
    ob = Observer()
    watch = ob.schedule(handler, path='.')
    ob.start()

    asyncio.get_event_loop().run_until_complete(watchdog_run(ob, handler, host, port))

    return 0

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

if __name__ == '__main__':
    sys.exit(run())
