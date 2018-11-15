import os.path
import subprocess
import sys
import agent
import serial
import re
import time
#from robotlibcore import keyword

SCAN_TIMEOUT = 5        # seconds
CONNECT_TIMEOUT = 10    # seconds

class pingtest(object):

    def __init__(self):
        self._iperf_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'sut', 'login.py')
        self._status = ''
        self.serialport = None

    def __del__(self):
        if self.serialport is not None:
            self.serialport.close()

    #@keyword
    def connect_dut(self, deviceName):
        # raise AssertionError(str(sys.stdout))
        self.serialport = serial.Serial('COM9', 115200, timeout=0.5)

    def disconnect_dut(self, deviceName):
        if self.serialport is not None:
            self.serialport.close()

    def open_wifi(self, deviceName):
        pass

    def close_wifi(self, deviceName):
        pass

    def scan_networks(self, deviceName):
        self.serialport.write(b'wifi_scan\r')
        usedTime, result = self._serial_read(SCAN_TIMEOUT, 'scan finished')
        print('Scan used time {0}s'.format(usedTime))
        print(result)

    def connect_to_network(self, deviceName, ssid, password):
        self.serialport.write('wifi_connect {0} {1}\r'.format(ssid, password).encode())
        usedTime, result = self._serial_read(CONNECT_TIMEOUT, 'ip configured')
        print('Connecting used time {0}s'.format(usedTime))
        print(result)
    
    def ping(self, deviceName, target, times):
        ret = subprocess.call(['ping', '-n', times, '127.0.0.1'])
        if ret != 0:
            raise AssertionError('Running ping failed')
        return times

    def change_password(self, username, old_pwd, new_pwd):
        self._run_command('change-password', username, old_pwd, new_pwd)

    def status_should_be(self, expected_status):
        if expected_status != self._status:
            raise AssertionError("Expected status to be '%s' but was '%s'."
                                 % (expected_status, self._status))

    def _run_command(self, command, *args):
        command = [sys.executable, self._iperf_path, command] + list(args)
        process = subprocess.Popen(command, universal_newlines=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        self._status = process.communicate()[0].strip()

    def _serial_read(self, timeout, term=None):
        if term is not None:
            matcher = re.compile(term)
        tic = time.time()
        ret = b""
        buff = self.serialport.readline()
        while (time.time() - tic) < timeout:
            ret += buff
            if matcher and matcher.search(buff.decode()):
                break
            buff = self.serialport.readline()
        return time.time() - tic, ret.decode()
