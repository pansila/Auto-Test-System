import argparse
import asyncio
import importlib
import inspect
import json
import os
import os.path
import queue
import shutil
import signal
import site
import socket
import subprocess
import sys
import tarfile
import time
import traceback
import uuid
from contextlib import closing, contextmanager
from copy import copy
from io import BytesIO
from multiprocessing import Process, Queue
from pathlib import Path

import requests
import toml
import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from bson.objectid import ObjectId
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from wsrpc import WebsocketRPC

from .async_remote_library import AsyncRemoteLibrary
from .venv_run import activate_workspace, setup_multiprocessing_context

# import daemon as Daemon
# from daemoniker import Daemonizer, SignalHandler1


class TestLibraryServer:
    def __init__(self, process: Process, queue: Queue, url: str):
        self.process = process
        self.queue = queue
        self.url = url

    def __repr__(self):
        return f'url: {self.url}'

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
    old_path = sys.path
    eggs = [os.path.join(egg_path, f) for f in os.listdir(egg_path) if f.endswith('.egg')]
    sys.path[:0] = eggs
    yield
    sys.path = old_path

@contextmanager
def temp_environ_path(paths):
    old_path = os.environ['PATH']
    if paths:
        os.environ['PATH'] += os.pathsep + os.pathsep.join(paths)
    yield
    os.environ['PATH'] = old_path

class test_library_rpc_server(Process):
    def __init__(self, backing_file, task_id, config, queue, rpc_daemon=False, debug=False):
        super().__init__()
        self.backing_file = backing_file
        self.task_id = task_id
        self.config = config
        self.host = config['server_host']
        self.port = config['server_port']
        self.name = backing_file
        self.websocket = None
        self.loop = None
        self.rpc_daemon = rpc_daemon
        self.queue = queue
        self.debug = debug

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        if not self.rpc_daemon:
            pkg_data_dir = os.path.join(self.config['resource_dir'], 'package_data')
            test_data_dir = os.path.join(self.config['resource_dir'], 'test_data')
            if os.path.exists(pkg_data_dir):
                dirs = os.listdir(pkg_data_dir)
                dirs = list(map(lambda p: os.path.abspath(os.path.join(self.config['resource_dir'], 'package_data', p)), dirs))
            else:
                dirs = []
            if os.path.exists(test_data_dir):
                dirs.insert(0, os.path.abspath(test_data_dir))

            with install_eggs(self.config['download_dir']), temp_environ_path(dirs):
            # with activate_workspace('.'), install_eggs(self.config['download_dir']), temp_environ_path(dirs):
                task = asyncio.ensure_future(self.go())
                task.add_done_callback(self.task_done_check)
                try:
                    self.loop.run_until_complete(task)
                except KeyboardInterrupt:
                    pass
        else:
            task = asyncio.ensure_future(self.go())
            task.add_done_callback(self.task_done_check)
            try:
                self.loop.run_until_complete(task)
            except KeyboardInterrupt:
                pass

    def task_done_check(self, fut):
        try:
            fut.result()
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            print(exc_type, exc_value)
            traceback.print_tb(exc_tb)

    def get_test_library(self, test_module, module_name):
        test_lib = None
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
                return None
            test_lib = getattr(test_module, test_lib_name, None)
            if not test_lib:
                print(f'Could not find the test library {test_lib_name} in the module {module_name}')
                return None
        else:
            print(f'Could not find any test library in the module {module_name}')
            return None
        return test_lib

    def inform_caller_rpc_ready(self):
        self.queue.put(1)

    async def go(self):
        module_name = os.path.splitext(self.backing_file)[0].replace('//', '/').replace('/', '.')
        importlib.invalidate_caches()
        test_module = importlib.import_module(module_name)
        test_module = importlib.reload(test_module)
        test_lib = self.get_test_library(test_module, module_name)
        if not test_lib:
            return

        while True:
            try:
                async with websockets.connect(f'ws://{self.host}:{self.port}/api_v1/rpc_proxy/rpc') as rpc_ws, websockets.connect(f'ws://{self.host}:{self.port}/api_v1/rpc_proxy/msg') as msg_ws:
                    await rpc_ws.send(json.dumps({
                                   'join_id': self.config['join_id'],
                                   'uid': self.config['uuid'],
                                   'backing_file': self.backing_file if not self.rpc_daemon else ''
                                }))
                    try:
                        ret = await rpc_ws.recv()
                    except (ConnectionClosedOK, ConnectionClosedError):
                        print('Main server not ready')
                        await asyncio.sleep(10)
                        continue
                    else:
                        if self.debug:
                            print('server response message: ', ret)
                    if ret == 'OK':
                        self.inform_caller_rpc_ready()
                        print('Start the RPC server for ' + ('daemon' if self.rpc_daemon else 'test'))
                        try:
                            testlib = test_lib(self.config, self.task_id)
                            await SecureWebsocketRPC(rpc_ws, AsyncRemoteLibrary(testlib, rpc_ws, msg_ws, self.task_id, self.debug), method_prefix='').run()
                        except ConnectionClosedError:
                            print('Websocket closed')
                    elif ret == 'Unauthorized':
                        print('This endpoint is unauthorized, please authorize it on the WEB admin page')
                        await asyncio.sleep(10)
                        continue
                    else:
                        print('Received a message from the server: {}'.format(ret))
                        await asyncio.sleep(10)
                        continue
            except (ConnectionRefusedError, ConnectionClosedError):
                # print('Connection refused error while try connecting')
                pass
            if not self.rpc_daemon:
                print('Exit RPC server')
                break
            await asyncio.sleep(1)

def start_remote_server(backing_file, config, task_id=None, rpc_daemon=False, debug=False):
    if not rpc_daemon:
        with activate_workspace('workspace') as venv:
            #setup_multiprocessing_context()
            queue = Queue()
            process = test_library_rpc_server(backing_file, task_id, config, queue, rpc_daemon, debug)
            process.start()
    else:
        queue = Queue()
        process = test_library_rpc_server(backing_file, task_id, config, queue, rpc_daemon, debug)
        process.start()
    return TestLibraryServer(process, queue, backing_file)

def read_toml_config(config_file = "pyproject.toml", host=None, port=None):
    toml_config = toml.load(config_file)
    if 'join_id' not in toml_config['tool']['collie']['settings'] or not toml_config['tool']['collie']['settings']['join_id']:
        print("'join_id' must be specified in the pyproject.toml, it's either organization's id or team's id you want to join.")
        print("You can find it on the server's global settings sidebar")
        return None

    build_uuid = False
    if 'uuid' not in toml_config['tool']['collie']['settings'] or not toml_config['tool']['collie']['settings']['uuid']:
        build_uuid = True
    else:
        try:
            uuid.UUID(toml_config['tool']['collie']['settings']['uuid'])
        except Exception:
            build_uuid = True
    if build_uuid:
        toml_config['tool']['collie']['settings']['uuid'] = str(uuid.uuid1())
        with open(config_file, 'w') as fp:
            toml.dump(toml_config, fp)
        print('Generated the endpoint\'s uuid: ' + toml_config['tool']['collie']['settings']['uuid'] + ', please authorize it on the server\'s endpoint management page')

    config = {
        **toml_config['tool']['collie']['settings'],
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
    return config

def start_daemon(config, debug=False):
    return start_remote_server('test_endpoint/daemon.py', config, rpc_daemon=True, debug=debug)

class Config_Handler(FileSystemEventHandler):
    def __init__(self):
        self.restart = True

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("pyproject.toml"):
            self.restart = True

def watchdog_run(config_watchdog, handler, host, port, debug=False):
    daemon = None
    queue = None
    while config_watchdog.is_alive():
        if handler.restart:
            if daemon:
                daemon.terminate()
            config = read_toml_config(host=host, port=port)
            if not config:
                config_watchdog.stop()
                break
            # config = read_config(host=host, port=port)
            daemon = start_daemon(config, debug=debug).process
            handler.restart = False

        try:
            daemon.join(1)
        except KeyboardInterrupt:
            config_watchdog.stop()
            daemon.terminate()
            break

        if not daemon.is_alive():
            config_watchdog.stop()
            break
    else:
        daemon.terminate()

def run(host=None, port=None, debug=False):
    handler = Config_Handler()
    ob = Observer()
    watch = ob.schedule(handler, path='.')
    ob.start()

    watchdog_run(ob, handler, host, port, debug)

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
