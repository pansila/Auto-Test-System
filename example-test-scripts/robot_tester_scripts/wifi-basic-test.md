# Notes of Writing A Test Script

There are two ways to support a test suite in the markdown file.

1. Write the robot test case in the markdown code block.

   \``` robotframework

   \```
2. Write the robot test case in the markdown table.

   We use the second way to write our test cases as it's more legible for test writer

Because it's a distributed test system compared to a local standalone test system, some essential configurations need to be included at the beginning of the test script as follows.

* Include "Resource config.robot" to load the test related configuration
* Include "Library Remote <address:port>" to connect to an endpoint
* Include the dynamic "Import Library <address:port>" to connect to the test library for the downloaded test case

## Test Plans
- [Notes of Writing A Test Script](#notes-of-writing-a-test-script)
  - [Test Plans](#test-plans)
    - [Setup for all test cases](#setup-for-all-test-cases)
    - [Ping Test](#ping-test)
    - [iperf UDP RX test](#iperf-udp-rx-test)
    - [iperf TCP RX test](#iperf-tcp-rx-test)
    - [iperf UDP TX test](#iperf-udp-tx-test)
    - [iperf TCP TX test](#iperf-tcp-tx-test)

### Setup for all test cases

| Settings | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Resource | setup.robot |

| Variables | Value |
|---|---|
| ${dut1} | STA1 |
| ${ap_ssid} | Xiaomi3 |
| ${ap_password} | 12345678 |
| ${firmware} | firmware.bin |
| ${flash_address} | 0x08000000 |

| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Setup DUT |
| | [Arguments] | ${backing file} | ${testlib} | ${dut} |
| | Setup Remote | ${backing file} | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut} |
| Teardown DUT |
| | [Arguments] | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Teardown Remote |

### Ping Test

Notes:

1. There is no need to open WiFi here as it has been opened at boot-up time, we do it here to warm up the serial port ISR code to work around the character missing issue.
2. There might be a ping timeout error for the first request due to too long ARP handshake process, thus we require pass times one less than requests times at least to pass the test.
3. firmware and other resource files are uploaded to a certain directory in the endpoint, just use it in a relative path after uploaded

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|
| Ping test |
| | [Setup] | Setup DUT | pingtest.py | pingtestlib | ${dut1} |
| | [Teardown] | Teardown DUT | pingtestlib | ${dut1} |
| | pingtestlib.download | ${dut1} | ${firmware} | ${flash_address} |
| | pingtestlib.open wifi | ${dut1} |
| | pingtestlib.scan networks | ${dut1} |
| | pingtestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${ret} = | pingtestlib.ping | ${dut1} | AP | 5 |
| | Should Be True | ${ret} >= 4 |

### iperf UDP RX test

We only check whether a traffic is running successfully and throughput is not zero, no specific throughput requirements for basic test.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|
| iperf UDP RX test |
| | [Setup] | Setup DUT | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown DUT | iperftestlib | ${dut1} |
| | ${dut_ip} = | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=40M | time=10 | interval=1 |

### iperf TCP RX test
Reboot the device after the test due to a bug.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|
| iperf TCP RX test |
| | [Setup] | Setup DUT | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown DUT | iperftestlib | ${dut1} |
| | ${dut_ip} = | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 tcp rx | ${dut1} | ${dut_ip} | length=1000 | time=10 | interval=1 |
| | iperftestlib.reboot | ${dut1} |

### iperf UDP TX test
| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Teardown Iperf TX Server |
| | [Arguments] | ${daemon} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | Teardown DUT | ${testlib} | ${dut} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|
| iperf UDP TX test |
| | [Setup] | Setup DUT | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Iperf TX Server | iperftestlib | ${dut1} |
| | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=40M | time=10 |

### iperf TCP TX test

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|
| iperf TCP TX test |
| | [Setup] | Setup DUT | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Iperf TX Server | iperftestlib | ${dut1} |
| | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 tcp tx | ${dut1} | ${dut_ip} | length=1000 | time=10 |
