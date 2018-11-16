import os.path
import subprocess
import sys
import importlib
import shutil
import threading
import signal
import yaml
from robotremoteserver import RobotRemoteServer
#from robotlibcore import HybridCore

DOWNLOAD_LIB = "testlibs"

g_config = {}

class agent(object):

    def __init__(self):
        if os.path.exists(g_config["test_dir"]):
            shutil.rmtree(g_config["test_dir"])
        os.makedirs(g_config["test_dir"])
        self.tests = {}

    def start(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        if testcase in self.tests:
            self.tests[testcase]["server"].stop()
            del self.tests[testcase]

        self._download(testcase)
        self._verify(testcase)

        importlib.invalidate_caches()
        testlib = importlib.import_module(".%s" % testcase[0:-3], g_config["test_dir"])
        server, server_thread = start_server(testlib.pingtest(g_config), port=g_config["port_test"])
        if testcase not in self.tests:
            self.tests[testcase] = {"server": server, "thread": server_thread}
        return
        #importlib.invalidate_caches()
        #testlib = importlib.import_module(".iperftest", g_config["test_dir"])
        #libraries = [testlib.iperftest()]
        #HybridCore.__init__(self, libraries)
        #start_server(testlib.iperftest())

    def stop(self, testcase):
        if not testcase.endswith(".py"):
            testcase += ".py"

        if testcase in self.tests:
            self.tests[testcase]["server"].stop()
        else:
            raise AssertionError("test {0} is not running".format(testcase))

    def _download(self, testcase):
        # try:
        #     os.unlink(os.path.join(g_config["test_dir"], testcase))
        # except FileNotFoundError:
        #     pass
        shutil.copy(testcase, g_config["test_dir"])

    def _verify(self, testcase):
        testlib = os.path.join(g_config["test_dir"], testcase)
        if not os.path.exists(testlib):
            raise AssertionError("Downloading file %s failed" % testcase)

    def clear_log(self):
        pass

    def upload_log(self):
        pass

def start_server(testlib, port=8270):
    server = RobotRemoteServer(testlib, host=g_config["host"], serve=False, port=port)
    server_thread = threading.Thread(target=server.serve)
    server_thread.start()
    return server, server_thread

if __name__ == '__main__':
    with open('config.yml') as f:
        g_config = yaml.load(f)

    if "test_dir" not in g_config:
        g_config["test_dir"] = DOWNLOAD_LIB
    if "port_agent" not in g_config:
        g_config["port_agent"] = 8270
    if "port_test" not in g_config:
        g_config["port_test"] = 8271
    if "host" not in g_config:
        g_config["host"] = "127.0.0.1"

    server, server_thread = start_server(agent(), port=g_config["port_agent"])
    #signal.signal(signal.SIGHUG, lambda signum, frame: server.stop())
    server_thread.join()
    #while server_thread.is_alive():
    #    server_thread.join(0.1)

