import os.path
import subprocess
import sys
import importlib
import shutil
import threading
import signal
import yaml
import requests
from robotremoteserver import RobotRemoteServer
import tarfile
from distutils import dir_util
#from robotlibcore import HybridCore

DOWNLOAD_LIB = "testlibs"
TEMP_LIB = "temp"

g_config = {}

class agent(object):

    def __init__(self, config):
        self.tests = {}
        self.config = config
        if os.path.exists(self.config["test_dir"]):
            shutil.rmtree(self.config["test_dir"])
        os.makedirs(self.config["test_dir"])
        sys.path.insert(0, os.path.realpath(self.config["test_dir"]))

    def start_test(self, testcase):
        if testcase.endswith(".py"):
            testcase = testcase[0:-3]

        self._download(testcase)
        self._verify(testcase)

        if testcase in self.tests:
            print('Found remnant test case {}, stop the server {}.'.format(testcase, id(self.tests[testcase]["server"])))
        self.stop_test(testcase)

        importlib.invalidate_caches()
        testlib = importlib.import_module(testcase)
        importlib.reload(testlib)
        test = getattr(testlib, testcase)
        server, server_thread = start_remote_server(test(self.config),
                                    host=self.config["host_agent"],
                                    port=self.config["port_test"])
        self.tests[testcase] = {"server": server, "thread": server_thread}
        return
        #importlib.invalidate_caches()
        #testlib = importlib.import_module(".iperftest", self.config["test_dir"])
        #libraries = [testlib.iperftest()]
        #HybridCore.__init__(self, libraries)
        #start_server(testlib.iperftest())

    def stop_test(self, testcase):
        if testcase in self.tests:
            # self.tests[testcase]["server"].stop()
            # shutdown socket server directly since stop is an async operation, otherwise there could be out of order start/stop
            self.tests[testcase]["server"]._server.shutdown()
            del self.tests[testcase]["server"]
            del self.tests[testcase]
        else:
            print("test {} is not running".format(testcase))

    def _download(self, testcase):
        if testcase.endswith(".py"):
            testcase = testcase[0:-3]

        tarball = '{}.tgz'.format(testcase)
        url = "{}:{}/scripts/{}".format(self.config["server_url"], self.config["server_port"], testcase)
        print('Downloading test file {} from {}'.format(tarball, url))

        r = requests.get(url)
        if r.status_code == 404:
            raise AssertionError('Downloading test file {} failed'.format(tarball))

        output = '{}\\{}'.format(self.config['test_dir'], tarball)
        with open(output, 'wb') as f:
            f.write(r.content)
        print('Downloading test file {} succeeded'.format(tarball))

        with tarfile.open(output) as tarFile:
            tarFile.extractall(self.config["test_dir"])

        temp_dir = os.path.join(self.config['test_dir'], TEMP_LIB)
        dir_util.copy_tree(temp_dir, self.config['test_dir'])
        shutil.rmtree(temp_dir)

    def _verify(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        testlib = os.path.join(self.config["test_dir"], testcase)
        if not os.path.exists(testlib):
            raise AssertionError("Verify downloaded file %s failed" % testcase)
    
    def start(self):
        """ start the agent """
        pass

    def stop(self):
        """ stop the agent """
        pass

    def clear_log(self):
        pass

    def upload_log(self):
        pass

def start_remote_server(testlib, host, port=8270):
    server = RobotRemoteServer(testlib, host=host, serve=False, port=port)
    server_thread = threading.Thread(target=server.serve)
    server_thread.start()
    return server, server_thread

def start_agent(config_file = "config.yml"):
    global g_config
    with open(config_file) as f:
        g_config = yaml.load(f)

    if "test_dir" not in g_config:
        g_config["test_dir"] = DOWNLOAD_LIB
    if "port_agent" not in g_config:
        g_config["port_agent"] = 8270
    if "port_test" not in g_config:
        g_config["port_test"] = 8271
    if "host_agent" not in g_config:
        g_config["host_agent"] = "127.0.0.1"
    if "server_url" not in g_config:
        raise AssertionError('server is not set in the config file')
    else:
        if not g_config['server_url'].startswith('http://'):
            g_config['server_url'] += 'http://'
        if g_config['server_url'][-1] == '/':
            g_config['server_url'] = g_config['server_url'][0:-1]

    server, server_thread = start_remote_server(agent(g_config), host=g_config["host_agent"], port=g_config["port_agent"])
    signal.signal(signal.SIGBREAK, lambda signum, frame: server.stop())
    server_thread.join()

if __name__ == '__main__':
    try:
        start_agent()
    except OSError as err:
        print(err)
        print("Please check IP {} is configured correctly".format(g_config["host_agent"]))
