- [SoftAP Performance Test](#softap-performance-test)
- [Test Plans](#test-plans)
	- [Setup for all test cases](#setup-for-all-test-cases)
	- [iperf3 UDP TX test](#iperf3-udp-tx-test)
	- [iperf3 TCP TX test](#iperf3-tcp-tx-test)
	- [iperf3 UDP RX test](#iperf3-udp-rx-test)
	- [iperf3 TCP RX test](#iperf3-tcp-rx-test)
## SoftAP Performance Test
DUT creates a SoftAP with WPA2/AES. After network of SoftAP is ready, SUT will connect to it and do iperf3 test.

This test use ping test lib.
## Test Plans


### Setup for all test cases
| Settings | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Resource | config.robot |
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | ${endpoint_daemon} |

| Variables | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| ${dut1} | SOFTAP |
| ${endpoint_daemon} | EndpointDaemon1 |
| ${udp_len} | 1472 |
| ${tcp_len} | 1460 |
| ${bandwidth} | 40M |
| ${duration} | 190 |
| #AP LIST | SSID| PASSWORD | CHANNEL | HIDDEN |
| @{ap_security}| ft2019_performance_sec | 12345678 | 1 | 0 |


| Keywords | Value | Value | Value | Value | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|---|---|---|---|
| Setup Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} |
| | Run Keyword | ${daemon}.start test | ${testcase} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut1} |
| Teardown Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Run Keyword | ${daemon}.stop test | ${testcase} |
| |
| Create Network |
| | [Arguments] | ${dut} | ${testlib} | ${ssid} | ${passwd} | ${channel} | ${hidden} |
| | ${dut_ip} = | Run Keyword | ${testlib}.create softap | ${dut} | ${ssid} | ${passwd} | ${channel} | ${hidden} |
| | Run keyword | ${testlib}.sta scan |
| | Run Keyword | ${testlib}.sta connect network | ${ssid} | ${passwd} | ${hidden} |
|# Set STA PC static ip can be ignored
| | Run Keyword | ${testlib}.set sta static ip from source | ${dut_ip} |
| | ${sta_ip} = | Run Keyword | ${testlib}.sta get ip |
| | [Return] | ${dut_ip} | ${sta_ip} |
| Teardown Iperf3 TX Server |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | Teardown Remote | ${endpoint_daemon} | ${testcase} | ${testlib} | ${dut} |



### iperf3 UDP TX test
DUT create a SoftAP with WPA2/AES. Then pc station connect the SoftAP. Finnally, DUT do iperf3 udp tx test with pc station.
There is a issue that the lwip initial tcp port is same after DUT reboot, we need wait 35s for TIME_WAIT state timeout.


| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 UDP TX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | iperftestlib.download | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | iperftestlib | @{ap_security}[0] | @{ap_security}[1] | @{ap_security}[2] | @{ap_security}[3] |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=${udp_len} | bandwidth=${bandwidth} | time=${duration} |

### iperf3 TCP TX test
DUT create a SoftAP with WPA2/AES. Then pc station connect the SoftAP. Finnally, DUT do iperf3 tcp tx test with pc station.
There is a issue that the lwip initial tcp port is same after DUT reboot, we need wait 35s for TIME_WAIT state timeout.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 TCP TX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | iperftestlib | @{ap_security}[0] | @{ap_security}[1] | @{ap_security}[2] | @{ap_security}[3] |
| | ${dut_ip} = | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 tcp tx | ${dut1} | ${dut_ip} | length=${tcp_len} | time=${duration} |

### iperf3 UDP RX test
DUT create a SoftAP with WPA2/AES. Then pc station connect the SoftAP. Finnally, DUT do iperf3 udp rx test with pc station.


| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 UDP RX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | iperftestlib | @{ap_security}[0] | @{ap_security}[1] | @{ap_security}[2] | @{ap_security}[3] |
| | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 udp rx | ${dut1} | ${dut_ip} | length=${udp_len} | bandwidth=${bandwidth} | time=${duration} | interval=1 |
| | iperftestlib.reboot | ${dut1} |

### iperf3 TCP RX test
DUT create a SoftAP with WPA2/AES. Then pc station connect the SoftAP. Finnally, DUT do iperf3 tcp rx test with pc station.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 TCP RX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | iperftestlib | @{ap_security}[0] | @{ap_security}[1] | @{ap_security}[2] | @{ap_security}[3] |
| | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${tp} = | iperftestlib.iperf3 tcp rx | ${dut1} | ${dut_ip} | length=${tcp_len} | time=${duration} | interval=1 |
| | iperftestlib.reboot | ${dut1} |