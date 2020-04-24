import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from ruamel import yaml

import serial

from ..server_api import server_api


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
        dut['serialport'] = serial.Serial(dut['com'], dut['baudrate'], timeout=0.5)
        print('Serial port {} opened successfully'.format(dut['com']))

    def disconnect_dut(self, deviceName):
        dut = self.configDut[deviceName]
        if dut['serialport'] is not None:
            dut['serialport'].close()
            dut['serialport'] = None
        else:
            print('Serial port is not open')

    def reboot(self, deviceName):
        dut = self.configDut[deviceName]
        dut['serialport'].write(b'reboot\r')
        result = self._serial_read(deviceName, self.TIMEOUT, 'device opened')[0]
        print(result)

    def _serial_read(self, deviceName, timeout, term=None):
        '''
        Read the output of serial port.
        
        Arguments:
            timeout (int): the time to wait for before the read ends or term is found.
            term (str): a regexp to specify strings of interest to search in the output and early return if found (default None).

        Return a tuple consisting of:
            result (str): the output string of serial port
            elapsedTime (int): the time used by the read operation. TIMEOUT_ERR if timeout expires.
            groups (str): the captured groups by the regexp term
        '''
        dut = self.configDut[deviceName]

        match = None
        if term is not None:
            matcher = re.compile(term)
        tic = time.time()
        buff = dut['serialport'].readline()
        ret = buff

        while (time.time() - tic) < timeout:
            if term:
                match = matcher.search(buff.decode())
                if match:
                    break
            buff = dut['serialport'].readline()
            ret += buff
        else:
            return (ret.decode(), self.TIMEOUT_ERR, None)

        return (ret.decode(), time.time() - tic, match.groups() if match else None)

    def _flush_serial_output(self, deviceName, wait_time=1):
        '''
        Flush the output of serial port remained.

        Arguments:
            wait_time (int): the time to flush before it ends (default 1s).

        Returns:
            result (str): the flushed output of serial port.
        '''
        
        result = self._serial_read(deviceName, wait_time)[0]
        return result
