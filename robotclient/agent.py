import os.path
import subprocess
import sys
import importlib
import shutil
import threading
import signal
from robotremoteserver import RobotRemoteServer
#from robotlibcore import HybridCore

DOWNLOAD_LIB = "testlibs"

class agent(object):

    def __init__(self):
        if os.path.exists(DOWNLOAD_LIB):
            shutil.rmtree(DOWNLOAD_LIB)
        os.makedirs(DOWNLOAD_LIB)
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
        testlib = importlib.import_module(".pingtest", DOWNLOAD_LIB)
        server, server_thread = start_server(testlib.pingtest(), port=8271)
        if testcase not in self.tests:
            self.tests[testcase] = {"server": server, "thread": server_thread}
        return
        #importlib.invalidate_caches()
        #testlib = importlib.import_module(".iperftest", DOWNLOAD_LIB)
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
        # os.unlink(os.path.join(DOWNLOAD_LIB, testcase))
        shutil.copy(testcase, DOWNLOAD_LIB)

    def _verify(self, testcase):
        testlib = os.path.join(DOWNLOAD_LIB, testcase)
        if not os.path.exists(testlib):
            raise AssertionError("Downloading file %s failed" % testcase)

    def clear_log(self):
        pass

    def upload_log(self):
        pass

def start_server(testlib, port=8270):
    server = RobotRemoteServer(testlib, *sys.argv[1:], serve=False, port=port)
    server_thread = threading.Thread(target=server.serve)
    server_thread.start()
    return server, server_thread

if __name__ == '__main__':
    server, server_thread = start_server(agent())
    #signal.signal(signal.SIGHUG, lambda signum, frame: server.stop())
    server_thread.join()
    #while server_thread.is_alive():
    #    server_thread.join(0.1)

