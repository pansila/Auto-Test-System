import re

from customtestlibs.wifi_test import wifi_basic_test


class pingtest(wifi_basic_test):

    def ping(self, deviceName, target, times):
        ping_dst = target
        if target == "AP":
            ping_dst = self.IP_AP
        else:
            if re.compile(self.REGEXP_IP).match(target) is None:
                raise AssertionError("ping destination {0} is not a valid IP".format(target))

        dut = self.configDut[deviceName]
        dut['serialport'].write('ping {0} {1}\r'.format(ping_dst, times).encode())
        (result, elapsedTime, groups) = self._serial_read(deviceName, int(times)*2 + 2, r'(\d+) packets transmitted, (\d+) received')
        print(result)

        if elapsedTime == self.TIMEOUT:
            raise AssertionError('Ping timeout')
        if len(groups) != 2:
            raise AssertionError('Searching ping result failed')
        if groups[0] != times:
            raise AssertionError('Except pinging {0} times, but sent {1} packets only'.format(times, groups[0]))

        print('Ping used time {0}s'.format(elapsedTime))
        return groups[1]
