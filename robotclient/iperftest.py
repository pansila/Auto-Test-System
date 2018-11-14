import os.path
import subprocess
import sys
import agent
#from robotlibcore import keyword

class iperftest(object):

    def __init__(self):
        self._iperf_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'sut', 'login.py')
        self._status = ''

    #@keyword
    def connect_to_dut_device(self, deviceName):
        pass

    #@keyword
    def open_wifi(self, device):
        pass

    #@keyword
    def scan_networks(self):
        pass

    #@keyword
    def connect_to_network(self, username, password):
        pass
    
    #@keyword
    def ping(self, target, times):
        return times

    #@keyword
    def change_password(self, username, old_pwd, new_pwd):
        self._run_command('change-password', username, old_pwd, new_pwd)

    #@keyword
    def status_should_be(self, expected_status):
        if expected_status != self._status:
            raise AssertionError("Expected status to be '%s' but was '%s'."
                                 % (expected_status, self._status))

    def _run_command(self, command, *args):
        command = [sys.executable, self._iperf_path, command] + list(args)
        process = subprocess.Popen(command, universal_newlines=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        self._status = process.communicate()[0].strip()
