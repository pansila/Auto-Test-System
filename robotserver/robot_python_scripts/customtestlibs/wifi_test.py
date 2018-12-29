import os.path
import os
import sys
import re
from .device_test import device_test
from .winwifi import WinWiFi, WinIp
#from robotlibcore import keyword

class wifi_basic_test(device_test):
    SCAN_TIMEOUT = 5        # seconds
    CONNECT_TIMEOUT = 25    # seconds

    REGEXP_IP = r'(\d{1,3}(\.\d{1,3}){3})'

    def __init__(self, config):
        super().__init__(config)
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
            raise AssertionError('Connecting timeout')
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
    def sta_connect_network(self, ssid, passwd):
        '''
        @brief: Station like PC with Windows 7 or later OS connect wireless network with specific ssid
        we change stdout encoding to utf-8 since Chinese coding issue
        @param ssid: the wireless network name
        @param passwd: the wireless password
        '''
        interface = self.config['pc_nic']
        if os.name == 'nt' and sys.stdout.encoding != 'cp65001':
            os.system('chcp 65001 >nul 2>&1')
            WinWiFi.connect(ssid=ssid, passwd=passwd, remember=True, interface=interface)
        else:
            raise AssertionError("This os does't support yet!")


    def set_sta_static_ip_from_source(self, srcip, subMask='255.255.255.0'):
        '''
        @brief: This function allow you set a static ip that change from source ip to a interface that on Windows 7 or later PC
                And make sure this static ip can ping source ip.
                This is useful for iperf test.
        @param srcip: the source ip
        @param subMask: subnet mask
        '''
        s = WinIp()
        ip = srcip.split('.')
        interface = self.config['pc_nic']
        hostid = self.config['pc_host_id']
        s.set_static_ip(interface, ['{}.{}.{}.{}'.format(ip[0], ip[1], ip[2], hostid)], [subMask])
        s.ping(srcip)

    '''
    #TODO need to adapter new command
    def set_tx_rate(self, deviceName, rateIndex):
        self._flush_serial_output(deviceName)
        dut = self.configDut[deviceName]
        ret = re.compile(r'^[0][x][0-9a-fA-F]+$').search(rateIndex)
        if ret and ret.group():
            rate_index = int(rateIndex,16)
        else:
            ret = re.compile(r'^\d+$').search(rateIndex)
            if ret and ret.group():
                rate_index = int(rateIndex)
            else:
                raise AssertionError("arguments rate index is invalided")

        dut['serialport'].write('wifi_set_rate {0}'.format(rate_index).encode())
        (result, elapsedTime, _) = self._serial_read(deviceName, self.CONNECT_TIMEOUT, 'set tx rate')
        print(result)
        if elapsedTime == self.TIMEOUT_ERR:
            raise AssertionError('set tx rate timeout')
        print('Set tx rate used time {0}s'.format(elapsedTime))
        ret = re.compile(r'set\s+tx\s+rate\s+(\d+),\s+sgi\s+(\d+)').search(result)
        if ret and ret.groups():
            result_index = ret.groups()[0]
            result_sgi = ret.groups()[1]
            if int(result_index) != rate_index or (((rate_index & 0x80) >> 7) != int(result_sgi)) :
                raise AssertionError("set tx rate failed")
        else:
            raise AssertionError("set tx rate failed")
    '''
