## Test Plans
- [Test Plans](#test-plans)
	- [Setup for all test cases](#setup-for-all-test-cases)
	- [Ping Test](#ping-test)
	- [iperf3 UDP RX test](#iperf3-udp-rx-test)
	- [iperf3 TCP RX test](#iperf3-tcp-rx-test)
	- [iperf3 UDP TX test](#iperf3-udp-tx-test)
	- [iperf3 TCP TX test](#iperf3-tcp-tx-test)
	- [iperf2 UDP RX test](#iperf2-udp-rx-test)
	- [iperf2 TCP RX test](#iperf2-tcp-rx-test)
	- [iperf2 UDP TX test](#iperf2-udp-tx-test)
	- [iperf2 TCP TX test](#iperf2-tcp-tx-test)

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

### iperf3 UDP RX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf3 UDP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 | interval=1 |

### iperf3 TCP RX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf3 TCP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf3 start rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 tcp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 | interval=1 |

### iperf3 UDP TX test
| Keywords | Value | Value | Value | Value | Value |
|---|
| Teardown Iperf3 TX Server |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | Teardown Remote | ${endpoint_agent} | ${testcase} | ${testlib} | ${dut} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf3 UDP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 |

### iperf3 TCP TX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf3 TCP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf3 start tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf3 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 |

### iperf2 UDP RX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf2 UDP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf2 start udp rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf2 udp rx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 | interval=1 |

### iperf2 TCP RX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf2 TCP RX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | ${dut_ip} = | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | Run Keyword | iperftestlib.iperf2 start tcp rx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf2 tcp rx | ${dut1} | ${dut_ip} | length=1000 | time=10 | interval=1 |

### iperf2 UDP TX test
| Keywords | Value | Value | Value | Value | Value |
|---|
| Teardown Iperf2 TX Server |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf2 stop tx server |
| | Teardown Remote | ${endpoint_agent} | ${testcase} | ${testlib} | ${dut} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf2 UDP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf2 TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf2 start udp tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf2 udp tx | ${dut1} | ${dut_ip} | length=1000 | bandwidth=10M | time=10 |

### iperf2 TCP TX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|
| iperf2 TCP TX test |
| | [Setup] | Setup Remote | ${endpoint_agent} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf2 TX Server | ${endpoint_agent} | iperftest | iperftestlib | ${dut1} |
| | Run Keyword | iperftestlib.connect to network | ${dut1} | ${ap_ssid} | ${ap_password} |
| | ${dut_ip} = | Run Keyword | iperftestlib.iperf2 start tcp tx server | ${dut1} |
| | ${ret} = | Run Keyword | iperftestlib.iperf2 tcp tx | ${dut1} | ${dut_ip} | length=1000 | time=10 |
