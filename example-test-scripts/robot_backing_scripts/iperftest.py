from customtestlibs.wifi_test import wifi_basic_test
import subprocess
from subprocess import PIPE
import threading
import queue
import ipaddress
import netifaces
import time
import re
from mongoengine import *
from customtestlibs.database import TestResult, Test
import datetime

class IperfTestResult(TestResult):
    firmware_revision = StringField(max_length=100)
    test_tool = StringField(max_length=50)
    test_type = StringField(max_length=10)
    direction = StringField(max_length=10)
    throughput = IntField()
    total_bytes = IntField()
    throughput_hum = StringField(max_length=50)

class iperftest(wifi_basic_test):
    unit_conversion = {
        '': 1,
        'K': 1024,
        'M': 1024*1024,
        'G': 1024*1024*1024,
    }

    def __init__(self, config):
        super().__init__(config)
        self.iperf_process = None
        self.iperf_queue = None
        test_result = IperfTestResult()
        test_result.test_case = 'Throughput Test'
        test_result.test_suite = Test.objects(test_suite='wifi-basic-test').get()
        test_result.test_site = '@'.join((self.config['name'], self.config['location']))
        test_result.tester = 'John'
        test_result.tester_email = 'John@123.com'
        test_result.save()
        self.test_result_id = test_result.pk

    def _unit_convert_to_digit(self, input):
        input = input.strip()
        if input.endswith('bits/sec'):
            input = input[0:-8]
        if input.endswith('Bytes'):
            input = input[0:-5]
        if input[-1].isdigit():
            return float(input)
        if input[-1] in self.unit_conversion:
            return float(input[0:-1]) * self.unit_conversion[input[-1]]
        raise AssertionError('Unknown digit format {}'.format(input))

    def _unit_convert_to_string(self, input):
        tmp = input
        rest = 0
        unit = None
        for u in self.unit_conversion.keys():
            unit = u
            if tmp >= 1024:
                rest = tmp % 1024
                tmp = tmp // 1024
            else:
                break
        return '{:d}.{:d} {}bits/sec'.format(tmp, rest, unit)

    def handle_test_result(self, reg, testLog):
        m = reg.search(testLog)
        if m and m.groups():
            print(m.groups())
            (rx_bytes, rx_bandwidth_hum) = m.groups()
            rx_bytes = self._unit_convert_to_digit(rx_bytes)
            rx_bandwidth = self._unit_convert_to_digit(rx_bandwidth_hum)
        else:
            raise AssertionError("Can't find test result in the iperf test")

        if rx_bandwidth < 1:
            raise AssertionError('No traffic found in the iperf test')

        result = {
            'status': 'Pass',
            'throughput': rx_bandwidth,
            'total_bytes': rx_bytes,
            'throughput_hum': rx_bandwidth_hum,
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**result)
        return result




    #################### RX test ####################
    ## RX server
    def iperf3_start_rx_server(self, deviceName):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write('iperf -s\r'.encode())
        result = self._serial_read(deviceName, self.TIMEOUT, 'Server listening')[0]
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf RX server on the DUT failed')

    def iperf3_stop_rx_server(self, deviceName):
        pass

    def iperf2_start_tcp_rx_server(self, deviceName):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write('tcp -s -i 1\r'.encode())
        result = self._serial_read(deviceName, self.TIMEOUT)[0]
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf TCP RX server on the DUT failed')

    def iperf2_start_udp_rx_server(self, deviceName):
        self._flush_serial_output(deviceName)

        dut = self.configDut[deviceName]
        dut['serialport'].write('udp -s -i 1\r'.encode())
        result = self._serial_read(deviceName, self.TIMEOUT)[0]
        print(result)
        if 'error' in result or 'ERROR' in result:
            raise AssertionError('Starting iperf UDP RX server on the DUT failed')

    ## RX client
    def iperf_rx(self, deviceName, host, iperf, type, length, bandwidth, time, interval):
        '''
        iperf RX test

        Arguments:
            host (str): test host IP address.
            iperf (str): the iperf client type, iperf2 and iperf3 are supported.
            type (str): the stream type, udp and tcp are supported.
            length (str): length of buffer to read or write.
            bandwidth (str): bandwidth to send at in bits/sec or packets per second.
            time (str): time in seconds to transmit.
            interval (str): seconds between periodic bandwidth reports.

        Returns:
            rx_log (str): log generated by receiver.
            tx_log (str): log generated by transmitter.
        '''
        if iperf not in self.config:
            raise AssertionError('Executable {} is not set in the config file, please check it'.format(iperf))

        arguments = [self.config[iperf], '-c', host]
        if type.lower() == 'udp':
            arguments.append('-u')

        # looks like a robot bug that non-assigned argument is given a string 'None'
        if length is not None and length != 'None':
            arguments.extend(['-l', length])
        if bandwidth is not None and bandwidth != 'None':
            arguments.extend(['-b', bandwidth])
        if time is not None and time != 'None':
            arguments.extend(['-t', time])
        if interval is not None and interval != 'None':
            arguments.extend(['-i', interval])

        p = subprocess.Popen(arguments, stdout=PIPE, stderr=PIPE)

        # First get the console log generated during the test.
        # windows buffer size is 4k, it may lose log.
        rx_log = self._serial_read(deviceName, int(time) + 10)[0]
        print('==== Receiver log ====')
        print(rx_log)

        (tx_log, error) = p.communicate()
        tx_log = tx_log.decode()
        print('==== Transmitter log ====')
        print('Command: {}'.format(' '.join(arguments)))
        print(tx_log)
        if error != b'':
            if b'error' in error:
                raise AssertionError('iperf test error: {}'.format(error))
            else:
                print(error)
        if 'error' in tx_log:
            raise AssertionError('iperf test error: {}'.format(tx_log))

        if rx_log == '' or tx_log == '':
            raise AssertionError('Running iperf test failed')

        return rx_log, tx_log

    # python is capable of overloading but we still provide different interfaces for convenience of use in the test table
    def iperf3_udp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf3',
            'test_type': 'UDP',
            'direction': 'RX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_rx(deviceName, host, 'iperf3', 'UDP', length, bandwidth, time, interval)
        # [  2]   0.00-4.00   sec  4.78 MBytes  10.0 Mbits/sec  1.468 ms  1667/4651 (36%)
        p = re.compile(r'sec\s+(\d+\.?\d*\s+\w?)Bytes\s+(\d+\.?\d*\s+\w?bits/sec)\s+receiver')
        result = self.handle_test_result(p, rx_log)

        return result['throughput']

    def iperf3_tcp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf3',
            'test_type': 'TCP',
            'direction': 'RX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        _, tx_log = self.iperf_rx(deviceName, host, 'iperf3', 'TCP', length, bandwidth, time, interval)
        # [  2]   0.00-4.00   sec  4.78 MBytes  10.0 Mbits/sec  1.468 ms  1667/4651 (36%)
        p = re.compile(r'sec\s+(\d+\.?\d*\s+\w?)Bytes\s+(\d+\.?\d*\s+\w?bits/sec)\s+receiver')
        result = self.handle_test_result(p, tx_log)

        return result['throughput']

    def iperf2_udp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf2',
            'test_type': 'UDP',
            'direction': 'RX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_rx(deviceName, host, 'iperf2', 'UDP', length, bandwidth, time, interval)
        # find the result in the lines like "0 - <d> sec ..." except for the first line "0 - 1 sec ..."
        p = re.compile(r'Total\s+0\s+-\s+\d+\s+sec\s+(\d+\s+\w?)Bytes\s+(\d+\s+\w?)bps')
        result = self.handle_test_result(p, rx_log)

        return result['throughput']

    def iperf2_tcp_rx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf2',
            'test_type': 'TCP',
            'direction': 'RX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_rx(deviceName, host, 'iperf2', 'TCP', length, bandwidth, time, interval)
        # find the result in the lines like "0 - <d> sec ..." except for the first line "0 - 1 sec ..."
        p = re.compile(r'Total\s+0\s+-\s+\d+\s+sec\s+(\d+\s+\w?)Bytes\s+(\d+\s+\w?)bps')
        result = self.handle_test_result(p, rx_log)

        return result['throughput']

    #################### TX test ####################
    ## TX server
    def _run_iperf_server(self, arguments, queue):
        p = subprocess.Popen(arguments, stdout=PIPE, stderr=PIPE)
        queue.put(p)
        cnt = 0
        while True:
            output = p.stdout.readline()
            if not output and p.poll() is not None:
                break
            if output:
                queue.put(output.decode())
            if (cnt & 0xF) == 0:    # to ease the cpu usage
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
            self.iperf_process = None
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
        iperf TX test.

        Arguments:
            host (str): test host IP address.
            iperf (str): the iperf client type, iperf2 and iperf3 are supported.
            type (str): the stream type, udp and tcp are supported.
            length (str): length of buffer to read or write.
            bandwidth (str): bandwidth to send at in bits/sec or packets per second.
            time (str): time in seconds to transmit.
            interval (str): seconds between periodic bandwidth reports.

        Returns:
            rx_log (str): log generated by receiver.
            tx_log (str): log generated by transmitter.
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

        self._flush_serial_output(deviceName)
        dut = self.configDut[deviceName]
        dut['serialport'].write(' '.join(arguments).encode())
        tx_log = self._serial_read(deviceName, self.TIMEOUT)[0]
        print(tx_log)
        if 'error' in tx_log.lower():
            raise AssertionError('Starting iperf TX client on the DUT failed')

        # read the remained console log by the test
        tx_log = self._serial_read(deviceName, int(time) + 10)[0]
        print('==== Transmitter log ====')
        print(tx_log)

        print('==== Receiver log ====')
        rx_log = ''
        while True:
            try:
                rx_log += self.iperf_queue.get(timeout=1)
            except queue.Empty:
                break
        print(rx_log)
        if rx_log == '' or tx_log == '':
            raise AssertionError('Running iperf test failed')

        if 'error' in rx_log.lower() or 'error' in tx_log.lower():
            raise AssertionError('Something wrong happened during iperf running')

        return rx_log, tx_log

    def iperf3_udp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf3',
            'test_type': 'UDP',
            'direction': 'TX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        _, tx_log = self.iperf_tx(deviceName, host, 'iperf3', 'UDP', length, bandwidth, time, interval)
        # there is a bug in iperf3 PC server statistics for UDP, we use iperf3 client's report instead
        # [  2]   0.00-4.00   sec  4.78 MBytes  10.0 Mbits/sec  1.468 ms  1667/4651 (36%)
        p = re.compile(r'\s+0\.0+\s*-\s*\d+\.?\d*\s+sec\s+(\d+\.?\d*\s+\w?)Bytes\s+(\d+\.?\d*\s+\w?bits/sec)\s+receiver')
        result = self.handle_test_result(p, tx_log)

        return result['throughput']

    def iperf3_tcp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf3',
            'test_type': 'TCP',
            'direction': 'TX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_tx(deviceName, host, 'iperf3', 'TCP', length, bandwidth, time, interval)
        # [  2]   0.00-4.00   sec  4.78 MBytes  10.0 Mbits/sec  1.468 ms  1667/4651 (36%)
        p = re.compile(r'\s+0\.0+\s*-\s*\d+\.?\d*\s+sec\s+(\d+\.?\d*\s+\w?)Bytes\s+(\d+\.?\d*\s+\w?bits/sec)\s+receiver')
        result = self.handle_test_result(p, rx_log)

        return result['throughput']

    def iperf2_udp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf2',
            'test_type': 'UDP',
            'direction': 'TX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_tx(deviceName, host, 'iperf2', 'UDP', length, bandwidth, time, interval)
        # find the result in the lines like "0.0 - <d>.<d> sec ..." except for the first line "0 - 1.0 sec ..."
        p = re.compile(r'\s+0\.0\s*-\s*(?!1\.?0\s+)\d+\.?\d*\s+sec\s+(\d+\.?\d+\s+\w?)Bytes\s+(\d+\.?\d+\s+\w?bits/sec)')

        result = self.handle_test_result(p, rx_log)

        return result['throughput']

    def iperf2_tcp_tx(self, deviceName, host, length=None, bandwidth=None, time=None, interval=None):
        update = {
            'test_date': datetime.datetime.utcnow(),
            'duration': time,
            'test_tool': 'iperf2',
            'test_type': 'TCP',
            'direction': 'TX',
        }
        IperfTestResult.objects(pk=self.test_result_id).update(**update)

        rx_log, _ = self.iperf_tx(deviceName, host, 'iperf2', 'TCP', length, bandwidth, time, interval)
        # find the result in the lines like "0.0 - <d>.<d> sec ..." except for the first line "0 - 1.0 sec ..."
        p = re.compile(r'\s+0\.0\s*-\s*(?!1\.?0\s+)\d+\.?\d*\s+sec\s+(\d+\.?\d+\s+\w?)Bytes\s+(\d+\.?\d+\s+\w?bits/sec)')

        result = self.handle_test_result(p, rx_log)

        return result['throughput']