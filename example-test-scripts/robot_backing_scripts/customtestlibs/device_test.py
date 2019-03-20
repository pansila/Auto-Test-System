import serial
import re
import time
import subprocess
import os
from pathlib import Path
import sys
from .database import MongoDBClient
import pexpect

class device_test(MongoDBClient):
    TIMEOUT_ERR = -1
    TIMEOUT = 1

    def __init__(self, config):
        super().__init__(config)
        self.config = config
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

    def download(self, deviceName, target=None):
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
                cmd = [d['path'], '-device', d['device'], '-if', d['interface'], '-speed', str(d['speed']), '-autoconnect', '1']
                if os.name == 'nt':
                    from pexpect import popen_spawn
                    a = popen_spawn.PopenSpawn(' '.join(cmd), encoding='utf-8')
                elif os.name == 'posix':
                    a = pexpect.spawn(' '.join(cmd), encoding='utf-8')
                else:
                    raise AssertionError('Not supported OS {}'.format(os.name))

                try:
                    a.expect_exact('J-Link>', timeout=5)
                except:
                    a.kill(9)
                    raise AssertionError('J-Link running failed')

                if os.path.isabs(d['datafile']):
                    data_file = Path(d['datafile'])
                else:
                    data_file = Path(self.config["resource_dir"]) / d['datafile']

                cmds = ['r', 'exec EnableEraseAllFlashBanks', 'erase', 'loadbin {} {:x} SWDSelect'.format(data_file, d['flash_addr']),
                        'verifybin {} {:x}'.format(data_file, d['flash_addr']), 'r', 'g']
                for c in cmds:
                    a.sendline(c)
                    idx = a.expect_list([re.compile('J-Link>'), re.compile('failed'), pexpect.TIMEOUT], timeout=120, searchwindowsize=10)
                    if idx != 0:
                        a.kill(9)
                        raise AssertionError('JLink command "{}" failed:\n{}\n{}'.format(c, a.before, a.after))
                    # print(a.before)
                a.sendline('qc')
                a.expect(pexpect.EOF)
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
        # print(result)
        return result