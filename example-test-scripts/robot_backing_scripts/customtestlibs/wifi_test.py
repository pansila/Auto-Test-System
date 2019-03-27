import os.path
import re

from .device_test import device_test

class wifi_basic_test(device_test):
    SCAN_TIMEOUT = 5        # seconds
    CONNECT_TIMEOUT = 25    # seconds

    REGEXP_IP = r'(\d{1,3}(\.\d{1,3}){3})'

    def __init__(self, config, task_id):
        super().__init__(config, task_id)
        self._iperf_path = os.path.join(os.path.dirname(__file__),
                                      '..', 'sut', 'login.py')
        self.ip_AP = None
        self.ip_DUT = None

    def open_wifi(self, deviceName):
        dut = self.configDut[deviceName]
        dut['serialport'].write(b'wifi_open\r')
        result = self._serial_read(deviceName, self.TIMEOUT)[0]
        print(result)

    def close_wifi(self, deviceName):
        dut = self.configDut[deviceName]
        dut['serialport'].write(b'wifi_close\r')
        result = self._serial_read(deviceName, self.TIMEOUT)[0]
        print(result)

    def scan_networks(self, deviceName):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write(b'wifi_scan\r')
        (result, elapsedTime, _) = self._serial_read(deviceName, self.SCAN_TIMEOUT, 'scan finished')
        print(result)

        if elapsedTime == self.TIMEOUT_ERR:
            raise AssertionError('Scan timeout')
        print('Scan used time {0}s'.format(elapsedTime))

    def connect_to_network(self, deviceName, ssid, password):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write('wifi_connect {0} {1}\r'.format(ssid, password).encode())
        (result, elapsedTime, _) = self._serial_read(deviceName, self.CONNECT_TIMEOUT, 'ip configured')
        print(result)

        if elapsedTime == self.TIMEOUT_ERR:
            raise AssertionError('Connecting to {} timeout'.format(ssid))
        print('Connecting used time {0}s'.format(elapsedTime))

        ret = re.compile('IP: {0}'.format(self.REGEXP_IP)).search(result)
        if ret and ret.groups():
            self.ip_DUT = ret.groups()[0]
            ip = self.ip_DUT.split('.')
            ip.pop()
            ip.append('1')
            self.IP_AP = '.'.join(ip)
        else:
            raise AssertionError("Can't get device's IP")
        return self.ip_DUT

    def disconnect_network(self, deviceName):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write(b'wifi_disconnect\r')
        (result, elapsedTime, _) = self._serial_read(deviceName, self.CONNECT_TIMEOUT, 'Stop DHCP')
        print(result)

        if elapsedTime == self.TIMEOUT_ERR:
            raise AssertionError('Disconnecting timeout')
        print('Disconnecting used time {0}s'.format(elapsedTime))
