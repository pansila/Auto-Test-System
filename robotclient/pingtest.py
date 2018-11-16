import os.path
import subprocess
import sys
import agent
import serial
import re
import time
import yaml
#from robotlibcore import keyword

TIMEOUT = -1
SCAN_TIMEOUT = 5        # seconds
CONNECT_TIMEOUT = 10    # seconds
PING_TIMEOUT = 10    # seconds

REGEXP_IP = r'(\d{1,3}(\.\d{1,3}){3})'

class pingtest(object):

    def __init__(self, config):
        self._iperf_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'sut', 'login.py')
        self._status = ''
        self.serialport = None
        self.IP_AP = None
        self.config = config

    def __del__(self):
        if self.serialport is not None:
            self.serialport.close()

    #@keyword
    def connect_dut(self, deviceName):
        for dut in self.config['DUT']:
            if deviceName != dut['name']:
                continue
            self.serialport = serial.Serial(dut['com'], dut['baudrate'], timeout=0.5)
            break

    def disconnect_dut(self, deviceName):
        if self.serialport is not None:
            self.serialport.close()
            self.serialport = None

    def open_wifi(self, deviceName):
        pass

    def close_wifi(self, deviceName):
        pass

    def scan_networks(self, deviceName):
        self.serialport.write(b'wifi_scan\r')
        elapsedTime, result, _ = self._serial_read(SCAN_TIMEOUT, 'scan finished')
        print(result)

        if elapsedTime == TIMEOUT:
            raise AssertionError('Scan timeout')
        print('Scan used time {0}s'.format(elapsedTime))

    def connect_to_network(self, deviceName, ssid, password):
        self.serialport.write('wifi_connect {0} {1}\r'.format(ssid, password).encode())
        elapsedTime, result, _ = self._serial_read(CONNECT_TIMEOUT, 'ip configured')
        print(result)

        if elapsedTime == TIMEOUT:
            raise AssertionError('Connecting timeout')
        print('Connecting used time {0}s'.format(elapsedTime))

        ret = re.compile('IP: {0}'.format(REGEXP_IP)).search(result)
        if ret and ret.groups():
            ip = ret.groups()[0].split('.')
            ip.pop()
            ip.append('1')
            self.IP_AP = '.'.join(ip)
        else:
            raise AssertionError("Can't get device's IP")
    
    def ping(self, deviceName, target, times):
        ping_dst = target
        if target == "AP":
            ping_dst = self.IP_AP
        else:
            if re.compile(REGEXP_IP).match(target) is None:
                raise AssertionError("ping destination {0} is not a valid IP".format(target))

        self.serialport.write('ping {0} {1}\r'.format(ping_dst, times).encode())
        elapsedTime, result, groups = self._serial_read(int(times)*2 + 2, r'(\d+) packets transmitted, (\d+) received')
        print(result)

        if elapsedTime == TIMEOUT:
            raise AssertionError('Ping timeout')
        if len(groups) != 2:
            raise AssertionError('Searching ping result failed')
        if groups[0] != times:
            raise AssertionError('Except pinging {0} times, but sent {1} packets only'.format(times, groups[0]))

        print('Ping used time {0}s'.format(elapsedTime))
        return groups[1]

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
        match = None
        if term is not None:
            matcher = re.compile(term)
        tic = time.time()
        ret = b""
        buff = self.serialport.readline()

        while (time.time() - tic) < timeout:
            ret += buff
            match = matcher.search(buff.decode())
            if match:
                break
            buff = self.serialport.readline()
        else:
            return TIMEOUT, ret.decode(), None

        return time.time() - tic, ret.decode(), match.groups() if match else None
