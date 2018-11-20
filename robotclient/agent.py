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
#from robotlibcore import HybridCore

DOWNLOAD_LIB = "testlibs"

g_config = {}

class agent(object):

    def __init__(self, config):
        self.tests = {}
        self.config = config
        if os.path.exists(self.config["test_dir"]):
            shutil.rmtree(self.config["test_dir"])
        os.makedirs(self.config["test_dir"])
        sys.path.insert(0, self.config["test_dir"])

    def start_test(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        if testcase in self.tests:
            self.tests[testcase]["server"].stop()
            del self.tests[testcase]

        self._download(testcase)
        self._verify(testcase)

        # importlib.invalidate_caches()
        testlib = importlib.import_module(testcase[0:-3])
        importlib.reload(testlib)
        server, server_thread = start_remote_server(testlib.pingtest(self.config), port=self.config["port_test"])
        if testcase not in self.tests:
            self.tests[testcase] = {"server": server, "thread": server_thread}
        return
        #importlib.invalidate_caches()
        #testlib = importlib.import_module(".iperftest", self.config["test_dir"])
        #libraries = [testlib.iperftest()]
        #HybridCore.__init__(self, libraries)
        #start_server(testlib.iperftest())

    def stop_test(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        if testcase in self.tests:
            self.tests[testcase]["server"].stop()
        else:
            raise AssertionError("test {0} is not running".format(testcase))

    def _download(self, testcase):
        url = "{0}:{1}/scripts/{2}".format(self.config["server_url"], self.config["server_port"], testcase)
        print('Downloading test file {0} from {1}'.format(testcase, url))
        r = requests.get(url)
        with open('{0}\\{1}'.format(self.config['test_dir'], testcase), 'wb') as f:
            f.write(r.content)
        print('Downloading test file {0} succeeded'.format(testcase))

    def _verify(self, testcase):
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

def start_remote_server(testlib, port=8270):
    server = RobotRemoteServer(testlib, host=g_config["host"], serve=False, port=port)
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
    if "host" not in g_config:
        g_config["host"] = "127.0.0.1"
    if "server_url" not in g_config:
        raise AssertionError('Server is not set in the config file')
    else:
        if not g_config['server_url'].startswith('http://'):
            g_config['server_url'] += 'http://'
        if g_config['server_url'][-1] == '/':
            g_config['server_url'] = g_config['server_url'][0:-1]

    server, server_thread = start_remote_server(agent(g_config), port=g_config["port_agent"])
    signal.signal(signal.SIGBREAK, lambda signum, frame: server.stop())
    server_thread.join()

if __name__ == '__main__':
    start_agent()
