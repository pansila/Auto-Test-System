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
1. [Iperf TCP TX test](#Iperf_TCP_TX_test)
1. [Iperf TCP RX test](#Iperf_TCP_RX_test)
1. [Iperf UDP TX test](#Iperf_UDP_TX_test)
1. [Iperf UDP RX test](#Iperf_UDP_RX_test)

### Ping Test
| Settings | Value | Value | Value | Value | Value |
|---|
| Resource | config.robot |
| Library | Remote | ${remote_agent_address} | 10 | WITH NAME | ${endpoint_agent} |

| Variables | Value |
|---|
| ${dut1} | STA1 |
| ${dut2} | STA2 |
| ${endpoint_agent} | EndpointAgent1 |
| ${endpoint} | Endpoint1 |
| ${ap_ssid} | tplink886 |
| ${ap_password} | 12345678 |

| Keywords | Value | Value | Value | Value | Value |
|---|
| Setup Remote |
| | [Arguments] | ${agent} | ${testcase} | |
| | Run Keyword | ${agent}.start test | ${testcase} | |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${endpoint} |
| Teardown Remote |
| | [Arguments] | ${agent} | ${testcase} | ${endpoint} | ${dut} |
| | Run Keyword | ${endpoint}.Disconnect Dut | ${dut} | |
| | Run Keyword | ${agent}.stop test | ${testcase} | |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|
| Ping test |
| | [Setup] | Setup Remote | ${endpoint_agent} | pingtest |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | pingtest | ${endpoint} | ${dut1} |
| | Run Keyword | ${endpoint}.Connect Dut | ${dut1} |
| | Run Keyword | ${endpoint}.scan networks | ${dut1} |
| | Run Keyword | ${endpoint}.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${ret} = | Run Keyword | ${endpoint}.ping | ${dut1} | AP | 5 |
| | Should Be Equal | ${ret} | 5 |
| | Run Keyword | ${endpoint}.Disconnect Dut | ${dut1} |
