import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

import pexpect
import serial

from .rest_api import rest_api


class device_test(rest_api):
    TIMEOUT_ERR = -1
    TIMEOUT = 1

    def __init__(self, config, task_id):
        super().__init__(config, task_id)
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

    def download(self, deviceName, firmwareName=None, flashAddr=None):
        dut = self.configDut[deviceName]
        if 'download' not in dut:
            raise AssertionError('Download method is not configured for {}'.format(deviceName))

        for d in dut['download']:
            if len(d) <= 1:
                print('download tool {} is not supported yet'.format(d['tool'] if 'tool' in d else d))
                continue

            if d['tool'].upper() == 'MDK':
                if os.name != 'nt':
                    print('MDK is only supported on Windows')
                    continue
                cmd = [d['path'], '-f', str(Path(d['workdir']) / d['project']), '-t', d['target']]
                subprocess.run(cmd, check=True)
                break

            if d['tool'].upper() == 'JLINK':
                if not firmwareName:
                    firmwareName = d['datafile']
                if not flashAddr:
                    flashAddr = d['flash_addr']
                    if not isinstance(d['flash_addr'], str):
                        flashAddr = '{:x}'.format(d['flash_addr'])
                if flashAddr.startswith('0x'):
                    flashAddr = flashAddr[2:]

                firmwarePath = Path(self.config["resource_dir"]) / firmwareName
                script = Path(self.config["tmp_dir"]) / 'download_script.jlink'
                script_contents = ("r\n"
                                   "exec EnableEraseAllFlashBanks\n"
                                   "erase\n"
                                   "loadbin {} {} SWDSelect\n"
                                   "verifybin {} {}\n"
                                   "r\n"
                                   "g\n"
                                   "qc\n".format(firmwarePath, flashAddr, firmwarePath, flashAddr))
                with open(script, 'w') as f:
                    f.write(script_contents)
                cmd = [d['path'], '-device', d['device'], '-if', d['interface'], '-speed', str(d['speed']), '-autoconnect', '1', '-CommanderScript', str(script)]
                subprocess.run(cmd, check=True)
                break
            print('Firmware downloading failed by {}, try next tool...'.format(d['tool'].upper()))
        else:
            raise AssertionError('Downloading firmware for {} failed'.format(deviceName))

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
