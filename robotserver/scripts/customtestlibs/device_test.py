import serial
import re
import time

class device_test(object):
    TIMEOUT_ERR = -1
    TIMEOUT = 1

    def __init__(self, config):
        self.config = config
        self.serialport = None

    def __del__(self):
        if self.serialport is not None:
            self.serialport.close()

    def connect_dut(self, deviceName):
        for dut in self.config['DUT']:
            if deviceName != dut['name']:
                continue
            self.serialport = serial.Serial(dut['com'], dut['baudrate'], timeout=0.5)
            print('Serial port {} opened successfully'.format(dut['com']))
            break
        else:
            raise AssertionError('Device {} is not found, please check config file for it'.format(deviceName))

    def disconnect_dut(self, deviceName):
        if self.serialport is not None:
            self.serialport.close()
            self.serialport = None
        else:
            print('Serial port is not open')
    
    def reboot(self, deviceName):
        self.serialport.write(b'reboot\r')
        result, _, _ = self._serial_read(self.TIMEOUT, 'device opened')
        print(result)

    def _serial_read(self, timeout, term=None):
        '''
        Read the output of serial port.
        
        Arguments:
            timeout (int): the time to wait for before the read ends or term is found.
            term (str): a regexp to specify strings of interest to search in the output and early return if found (default None).

        Returns:
            result (str): the output string of serial port
            elapsedTime (int): the time used by the read operation. TIMEOUT_ERR if timeout expires.
            groups (str): the captured groups by the regexp term
        '''
        match = None
        if term is not None:
            matcher = re.compile(term)
        tic = time.time()
        buff = self.serialport.readline()
        ret = buff

        while (time.time() - tic) < timeout:
            if term:
                match = matcher.search(buff.decode())
                if match:
                    break
            buff = self.serialport.readline()
            ret += buff
        else:
            return ret.decode(), self.TIMEOUT_ERR, None

        return ret.decode(), time.time() - tic, match.groups() if match else None

    def _flush_serial_output(self, wait_time=1):
        '''
        Flush the output of serial port remained.

        Arguments:
            wait_time (int): the time to flush before it ends (default 1s).

        Returns:
            result (str): the flushed output of serial port.
        '''
        
        result, _, _ = self._serial_read(wait_time)
        # print(result)
        return result