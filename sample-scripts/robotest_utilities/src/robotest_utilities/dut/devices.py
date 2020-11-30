import asyncio
import json
import os
import re
import subprocess
import sys
import serial
import aioserial
import time
import chardet
import os.path

from abc import ABCMeta, abstractmethod, abstractproperty
from pathlib import Path
from ruamel import yaml

from ..server_api import server_api
from ..download_fw import download_fw_intf


class serial_dut(server_api):
    TIMEOUT_ERR = -1
    TIMEOUT = 1

    def __init__(self, daemon_config, task_id):
        super().__init__(daemon_config, task_id)
        with open('config.yml', 'r', encoding='utf-8') as f:
            self.config = yaml.load(f, Loader=yaml.RoundTripLoader)

        self.configDut = {}
        for dut in self.config['DUT']:
            self.configDut[dut['name']] = dut

    def connect_dut(self, deviceName):
        if deviceName not in self.configDut:
            raise AssertionError('Device {} is not found, please check config file for it'.format(deviceName))

        dut = self.configDut[deviceName]
        dut['serialport'] = aioserial.AioSerial(port=dut['com'], baudrate=dut['baudrate'])
        print('Serial port {} opened successfully'.format(dut['com']))

    def disconnect_dut(self, deviceName):
        dut = self.configDut[deviceName]
        if dut['serialport'] is not None:
            dut['serialport'].close()
            dut['serialport'] = None
        else:
            print('Serial port is not open')

    async def serial_write(self, deviceName, outbytes):
        dut = self.configDut[deviceName]
        return await dut['serialport'].write_async(outbytes)

    async def serial_read(self, deviceName, timeout, term=None):
        '''
        Read the output of serial port.
        
        Arguments:
            deviceName (str): the DUT's name to perform the serial read operation
            timeout (int): the time to wait for before the read ends or term is found.
            term (str): a regexp to specify strings of interest to search in the output and early return if found (default None).

        Return a tuple consisting of:
            result (str): the output string of serial port
            elapsedTime (int): the time used by the read operation. TIMEOUT_ERR if timeout expires.
            groups (str): the captured groups by the regexp term
        '''
        ret = None
        encoding = None

        async def _read_loop(deviceName, term=None):
            nonlocal ret, encoding
            dut = self.configDut[deviceName]
            serialport = dut['serialport']

            match = None
            if term is not None:
                matcher = re.compile(term)
            tic = time.time()
            buff = await serialport.readline_async()
            ret = buff
            encoding = chardet.detect(buff)['encoding'] or 'utf-8'

            while True:
                if term:
                    match = matcher.search(buff.decode(encoding=encoding))
                    if match:
                        break
                buff = await serialport.readline_async()
                encoding = chardet.detect(buff)['encoding'] or encoding
                ret += buff

            return (ret.decode(encoding=encoding), time.time() - tic, match.groups() if match else None)

        try:
            return await asyncio.wait_for(_read_loop(deviceName, term), timeout)
        except asyncio.TimeoutError:
            return (ret.decode(encoding=encoding) if ret else None, self.TIMEOUT_ERR, None)

    def _flush_serial_output(self, deviceName):
        self.configDut[deviceName]['serialport'].reset_output_buffer()
        self.configDut[deviceName]['serialport'].reset_input_buffer()

class wifi_dut_base(serial_dut, download_fw_intf):
    __metaclass__ = ABCMeta

    SCAN_TIMEOUT = 5        # seconds
    CONNECT_TIMEOUT = 25    # seconds

    REGEXP_IP = r'(\d{1,3}(\.\d{1,3}){3})'

    def __init__(self, daemon_config, task_id):
        super().__init__(daemon_config, task_id)
        self.ip_AP = None
        self.ip_DUT = None
        self.SSID = None
        self.INFRA_MODE = None
        self.configAP = {}

        for ap in self.config['AP']:
            self.configAP[ap['name']] = ap

    @abstractmethod
    def dut_open_wifi(self, deviceName):
        pass

    @abstractmethod
    def dut_close_wifi(self, deviceName):
        pass

    @abstractmethod
    def dut_scan_networks(self, deviceName):
        pass

    @abstractmethod
    def dut_connect_to_network(self, deviceName, ssid, password):
        pass

    @abstractmethod
    def dut_disconnect_network(self, deviceName):
        pass

    @abstractmethod
    def dut_set_channel(self, deviceName, channel, bandwidth, offset):
        pass

    @abstractmethod
    def dut_create_softap(self, deviceName, ssid, passwd, channel, hidden):
        pass

    @abstractmethod
    def dut_reboot(self, deviceName):
        pass
