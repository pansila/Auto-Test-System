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
1. [Ping Test](#Ping_Test)
2. [iperf TCP TX test](#iperf_TCP_TX_test)
3. [iperf TCP RX test](#iperf_TCP_RX_test)
4. [iperf UDP TX test](#iperf_UDP_TX_test)
5. [iperf UDP RX test](#iperf_UDP_RX_test)

### Setup for all test cases

| Settings | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | EndpointDaemon1 |

| Variables | Value |
|---|---|
| ${task_id} | will be automatically filled by task runner |
| ${dut1} | STA1 |
| ${address_daemon} | 127.0.0.1 |
| ${port_daemon} | 8270 |
| ${port_test} | 8271 |
| ${remote_daemon_address} | http://${address_daemon}:${port_daemon} |
| ${remote_test_address} | http://${address_daemon}:${port_test} |
| ${ap_ssid} | Xiaomi3 |
| ${ap_password} | 12345678 |
| ${firmware} | firmware.bin |
| ${flash_address} | 0x08000000 |

| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Setup Remote |
| | [Arguments] | ${daemon} | ${backing file} | ${testlib} | ${dut} |
| | Run Keyword | ${daemon}.start test | ${TEST NAME} | ${backing file} | ${task_id} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut} |
| Teardown Remote |
| | [Arguments] | ${daemon} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Run Keyword | ${daemon}.stop test | ${TEST NAME} | ${TEST STATUS} |

### Ping Test

Notes:

1. There is no need to open WiFi here as it has been opened at boot-up time, we do it here to warm up the serial port ISR code to work around the character missing issue.
2. There might be a ping timeout error for the first request due to too long ARP handshake process, thus we require pass times one less than requests times at least to pass the test.
3. firmware and other resource files are uploaded to a certain directory in the endpoint, just use it in a relative path after uploaded

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|
| Ping test |
| | [Setup] | Setup Remote | EndpointDaemon1 | pingtest.py | pingtestlib | ${dut1} |
| | [Teardown] | Teardown Remote | EndpointDaemon1 | pingtestlib | ${dut1} |
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
| | [Setup] | Setup Remote | EndpointDaemon1 | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Remote | EndpointDaemon1 | iperftestlib | ${dut1} |
| | ${dut_ip} = | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=40M | time=10 | interval=1 |

### iperf TCP RX test
Reboot the device after the test due to a bug.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|
| iperf TCP RX test |
| | [Setup] | Setup Remote | EndpointDaemon1 | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Remote | EndpointDaemon1 | iperftestlib | ${dut1} |
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
| | Teardown Remote | EndpointDaemon1 | ${testlib} | ${dut} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|
| iperf UDP TX test |
| | [Setup] | Setup Remote | EndpointDaemon1 | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Iperf TX Server | EndpointDaemon1 | iperftestlib | ${dut1} |
| | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=40M | time=10 |

### iperf TCP TX test

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|
| iperf TCP TX test |
| | [Setup] | Setup Remote | EndpointDaemon1 | iperftest.py | iperftestlib | ${dut1} |
| | [Teardown] | Teardown Iperf TX Server | EndpointDaemon1 | iperftestlib | ${dut1} |
| | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 tcp tx | ${dut1} | ${dut_ip} | length=1000 | time=10 |
