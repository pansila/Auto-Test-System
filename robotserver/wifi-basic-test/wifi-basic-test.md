# Notes of Writing A Test Script
Since it's a distributed test system as opposed to a local test system, some essential configurations need to be included at the beginning of the test script as follows.
* Include "Resource config.robot" to load the test related configuration
* Include "Library Remote <address:port>" to connect to an endpoint
* Include the dynamic "Import Library <address:port>" to connect to the test library for the downloaded test case

## Test Plans
1. [Ping Test](#Ping_Test)
1. [WiFi Enable/Disable Test](#WiFi_Enable/Disable_Test)
1. [Connect/Disconnect Test](#Connect/Disconnect_Test)
1. [WiFi Password Test](#WiFi_Password_Test)
1. [iperf TCP TX test](#iperf_TCP_TX_test)
1. [iperf TCP RX test](#iperf_TCP_RX_test)
1. [iperf UDP TX test](#iperf_UDP_TX_test)
1. [iperf UDP RX test](#iperf_UDP_RX_test)

### Setup for all test cases
| Settings | Value | Value | Value | Value | Value |
|---|
| Resource | config.robot |
| Library | Remote | ${remote_agent_address} | 10 | WITH NAME | ${endpoint_agent} |

| Variables | Value |
|---|
| ${dut1} | STA1 |
| ${dut2} | STA2 |
| ${endpoint_agent} | EndpointAgent1 |
| ${ap_ssid} | huawei851 |
| ${ap_password} | 12345678 |

| Keywords | Value | Value | Value | Value | Value |
|---|
| Setup Remote |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} |
| | Run Keyword | ${agent}.start test | ${testcase} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut1} |
| Teardown Remote |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Run Keyword | ${testlib}.Stop Remote Server |
| | Run Keyword | ${agent}.stop test | ${testcase} |

### Ping Test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|
| Ping test |
| | [Setup] | Setup Remote | ${endpoint_agent} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | pingtest | pingtestlib | ${dut1} |
| | Run Keyword | pingtestlib.scan networks | ${dut1} |
| | Run Keyword | pingtestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${ret} = | Run Keyword | pingtestlib.ping | ${dut1} | AP | 5 |
| | Should Be Equal | ${ret} | 5 |

### iperf UDP RX test
| *Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf UDP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 | interval=1 |

### iperf TCP RX test
| *Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf TCP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 tcp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 | interval=1 |

### iperf UDP TX test
| Keywords | Value | Value | Value | Value | Value |
|---|
| Teardown Iperf TX Server |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | Teardown Remote | ${endpoint_agent} | ${testcase} | ${testlib} | ${dut} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf UDP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 |
| | Run Keyword | iperftestlib.iperf3 stop tx server |

### iperf TCP TX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf TCP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 |
