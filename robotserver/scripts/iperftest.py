from customtestlibs.wifi_test import wifi_basic_test
import subprocess
from subprocess import PIPE
import threading
import queue
import io
import ipaddress
import netifaces
import time

class iperftest(wifi_basic_test):

    def __init__(self, config):
        super().__init__(config)
        # self.stdoutIO = None
        # self.stderrIO = None
        self.iperf_process = None

    #################### RX test ####################
    ## RX server
    def iperf3_start_rx_server(self, deviceName):
        self._flush_serial_output()
        self.serialport.write('iperf -s\r'.encode())
        _, result, _ = self._serial_read(self.TIMEOUT, 'Server listening')
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf RX server on the DUT failed')

    def iperf2_start_tcp_rx_server(self, deviceName):
        self._flush_serial_output()
        self.serialport.write('tcp -s -i 1\r'.encode())
        _, result, _ = self._serial_read(self.TIMEOUT)
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf TCP RX server on the DUT failed')

    def iperf2_start_udp_rx_server(self, deviceName):
        self._flush_serial_output()
        self.serialport.write('udp -s -i 1\r'.encode())
        _, result, _ = self._serial_read(self.TIMEOUT)
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf UDP RX server on the DUT failed')

    ## RX client
    def iperf_rx(self, deviceName, host, iperf, type, length, bandwidth, time, interval):
        '''
            options to specify the iperf client arguments, details please check help of iperf.
                host: <test host IP address>, 
                length: <length of buffer to read or write>,
                bandwidth: <bandwidth to send at in bits/sec or packets per second>,
                time: <time in seconds to transmit>,
                interval: <seconds between periodic bandwidth reports>
        '''
        if iperf not in self.config:
            raise AssertionError('Executable {} is not set in the config file, please check it'.format(iperf))

        arguments = [self.config[iperf], '-c', host]
        if type.lower() == 'udp':
            arguments.append('-u')

        if length is not None:
            arguments.extend(['-l', length])
        if bandwidth is not None:
            arguments.extend(['-b', bandwidth])
        if time is not None:
            arguments.extend(['-t', time])
        if interval is not None:
            arguments.extend(['-i', interval])

        p = subprocess.Popen(arguments, stdout=PIPE, stderr=PIPE)
        (result, error) = p.communicate()
        if error != b'':
            raise AssertionError('iperf test error: {}'.format(error))
        if b'error' in result:
            raise AssertionError('iperf test error: {}'.format(result.decode()))
        print('==== Transmitter log ====')
        print('Command: {}'.format(' '.join(arguments)))
        print(result.decode())

        # flush the console log due to the test
        _, result, _ = self._serial_read(self.TIMEOUT)
        print('==== Receiver log ====')
        print(result)

    # python is capable of overloading but we still provide different interfaces for convenience of use in the test table
    def iperf3_udp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_rx(deviceName, host, 'iperf3', 'UDP', length, bandwidth, time, interval)

    def iperf3_tcp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_rx(deviceName, host, 'iperf3', 'TCP', length, bandwidth, time, interval)

    def iperf2_udp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_rx(deviceName, host, 'iperf2', 'UDP', length, bandwidth, time, interval)

    def iperf2_tcp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_rx(deviceName, host, 'iperf2', 'TCP', length, bandwidth, time, interval)

    #################### TX test ####################
    ## TX server
    def _run_iperf_server(self, arguments, queue):
        p = subprocess.Popen(arguments, stdout=PIPE, stderr=PIPE)
        queue.put(p)
        cnt = 0
        while True:
            output = p.stdout.readline()
            if output == '' and p.poll() is not None:
                break
            if output:
                queue.put(output.decode())
                # print(output.decode())
            if (cnt & 0xF) == 0:
                time.sleep(0.5)
            cnt += 1
        rc = p.poll()
        return rc

    def _get_local_host_ip(self):
        for i in netifaces.interfaces():
            if netifaces.AF_INET in netifaces.ifaddresses(i):
                for address in netifaces.ifaddresses(i)[netifaces.AF_INET]:
                    addr = address['addr']
                    netmask = address['netmask']
                    # mask out subnet bits
                    network = ipaddress.IPv4Address(int(ipaddress.IPv4Address(addr)) & int(ipaddress.IPv4Address(netmask)))
                    if ipaddress.IPv4Address(self.ip_DUT) in ipaddress.IPv4Network('{}/{}'.format(network, netmask)):
                        return addr
        else:
            raise AssertionError("Can't find an interface in the list {} falls in the same subnet of DUT {}".format(' '.join(host_ips), self.ip_DUT))

    def iperf_start_tx_server(self, deviceName, iperf, type=None):
        if iperf not in self.config:
            raise AssertionError('Executable {} is not set in the config file, please check it'.format(iperf))
        if self.ip_DUT is None:
            raise AssertionError('DUT IP is not set, make sure DUT has connected to a network')

        arguments = [self.config[iperf], '-s', '-i', '1']
        if iperf.lower() == 'iperf2' and type.lower() == 'udp':
            arguments.append('-u')
        print('Command: {}'.format(' '.join(arguments)))

        self.iperf_queue = queue.Queue()
        iperf_server = threading.Thread(target=self._run_iperf_server, args=(arguments, self.iperf_queue))
        iperf_server.start()
        try:
            self.iperf_process = self.iperf_queue.get(timeout=1)
        except queue.Empty:
            raise AssertionError('Starting iperf subprocess failed')

        return self._get_local_host_ip()

    def iperf_stop_tx_server(self):
        if self.iperf_process is not None:
            print('stopping iperf, pid {}'.format(self.iperf_process.pid))
            self.iperf_process.kill()
        else:
            print('iperf is not running')

    def iperf3_stop_tx_server(self):
        self.iperf_stop_tx_server()

    def iperf2_stop_tx_server(self):
        self.iperf_stop_tx_server()

    def iperf3_start_tx_server(self, deviceName):
        return self.iperf_start_tx_server(deviceName, 'iperf3')

    def iperf2_start_udp_tx_server(self, deviceName):
        return self.iperf_start_tx_server(deviceName, 'iperf2', 'UDP')

    def iperf2_start_tcp_tx_server(self, deviceName):
        return self.iperf_start_tx_server(deviceName, 'iperf2', 'TCP')

    ## TX client
    def iperf_tx(self, deviceName, host, iperf, type, length, bandwidth, time, interval):
        '''
            options to specify the iperf client arguments, details please check help of iperf.
                host: <test host IP address>, 
                length: <length of buffer to read or write>,
                bandwidth: <bandwidth to send at in bits/sec or packets per second>,
                time: <time in seconds to transmit>,
                interval: <seconds between periodic bandwidth reports>
        '''
        if iperf.lower() == 'iperf3':
            arguments = ['iperf', '-c', host]
            if type.lower() == 'udp':
                arguments.append('-u')
        elif iperf.lower() == 'iperf2':
            arguments = [type.lower(), '-c', host]
        else:
            raise AssertionError('Argument iperf is not correct, got {}'.format(iperf))

        # looks like a robot bug that non-assigned argument is given a string 'None'
        if length is not None and length != 'None':
            arguments.extend(['-l', length])
        if bandwidth is not None and bandwidth != 'None':
            arguments.extend(['-b', bandwidth])
        if time is not None and time != 'None':
            arguments.extend(['-t', time])
        if interval is not None and interval != 'None':
            arguments.extend(['-i', interval])
        arguments.append('\r')

        self._flush_serial_output()
        self.serialport.write(' '.join(arguments).encode())
        _, result, _ = self._serial_read(self.TIMEOUT)
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf TX client on the DUT failed')

        # read the remained console log by the test
        _, result, _ = self._serial_read(int(time) + 10)
        print('==== Transmitter log ====')
        print(result)

        print('==== Receiver log ====')
        output = ''
        while True:
            try:
                output += self.iperf_queue.get(timeout=1)
            except queue.Empty:
                break
        print(output)
        if 'error' in output.lower():
            raise AssertionError('Something wrong happened during iperf running')

    def iperf3_udp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_tx(deviceName, host, 'iperf3', 'UDP', length, bandwidth, time, interval)

    def iperf3_tcp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_tx(deviceName, host, 'iperf3', 'TCP', length, bandwidth, time, interval)

    def iperf2_udp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_tx(deviceName, host, 'iperf2', 'UDP', length, bandwidth, time, interval)

    def iperf2_tcp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        self.iperf_tx(deviceName, host, 'iperf2', 'TCP', length, bandwidth, time, interval)
