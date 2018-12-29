## Performance Test
We need take different APs to do DUT performance evaluation and comparison.
We setup AP that listed in the room. For each AP, DUT first connect it obtain IP by DHCP. And then STA (Windows 7 or later PC)
connect AP too, but would be set static ip that same subnet with DUT for network condition reason. Finally , it would run iperf test between DUT and STA.

This test use iperf test lib.

### Setup for all test cases
| Settings | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Resource | config.robot |
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | ${endpoint_daemon} |

| Variables | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| ${dut1} | STA1 |
| ${dut2} | STA2 |
| ${endpoint_daemon} | EndpointDaemon1 |
| ${test_result} | PASS |
| ${udp_len} | 1472 |
| ${tcp_len} | 1460 |
| ${bandwidth} | 40M |
| ${duration} | 180 |
| #AP LIST | SSID| PASSWORD | VENDOR | MANUFACTURER |
| @{ap_list}| tenda_ac15 | 12345678 | BCM | TENDA |
| ... | huawei851 | 12345678 | RealTeK | HUAWEI |
| ... | 360wifi | 12345678 | RealTeK | NETCORE |
| ... | ASUS | 12345678 | MTK | ASUS |
| ... | test_11n |  | Qualcomm | TP-LINK |




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
| Setup Network |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | ${testlib}.reboot | ${dut} |
| | Run Keyword | ${testlib}.scan networks | ${dut} |
| | ${dut_ip} | Run Keyword | ${testlib}.connect to network | ${dut} | ${ssid} | ${pwd} |
| | Run Keyword | ${testlib}.sta connect network| ${ssid} | ${pwd} |
| | Run Keyword | ${testlib}.set sta static ip from source | ${dut_ip} |
| | [Return] | ${dut_ip} |
| |
| Iperf3 Udp Rx |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | ${dut_ip}= | Run Keyword | Setup Network | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | ${testlib}.iperf3 start rx server | ${dut} |
| | ${tp} = | Run Keyword | ${testlib}.iperf3 udp rx | ${dut} | ${dut_ip} | length=${udp_len} | bandwidth=${bandwidth} | time=${duration} | interval=1 |
| | [Return] |  ${tp} |
| |
| Iperf3 Tcp Rx |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | ${dut_ip}= | Run Keyword | Setup Network | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | ${testlib}.iperf3 start rx server | ${dut} |
| | ${tp} = | Run Keyword | ${testlib}.iperf3 tcp rx | ${dut} | ${dut_ip} | length=${tcp_len} | time=${duration} | interval=1 |
| | [Return] |  ${tp} |
| |
| Iperf3 Udp Tx |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | Setup Network | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | ${dut_ip} = | Run Keyword | ${testlib}.iperf3 start tx server | ${dut} |
| | ${tp} = |  Run Keyword | ${testlib}.iperf3 udp tx | ${dut} | ${dut_ip} | length=${udp_len} | bandwidth=${bandwidth} | time=${duration} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | [Return] |  ${tp} |
| |
| Iperf3 Tcp Tx |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | Setup Network | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | ${dut_ip} = | Run Keyword | ${testlib}.iperf3 start tx server | ${dut} |
| | ${tp} = |  Run Keyword | ${testlib}.iperf3 tcp tx |  ${dut} | ${dut_ip} | length=${tcp_len} | time=${duration} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | [Return] |  ${tp} |


### iperf3 UDP RX test
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 UDP RX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${test_result}= | Set Variable | PASS |
| | :FOR |${ap_ssid} | ${ap_password} | ${ap_vendor} | ${ap_manu} | IN | @{ap_list}
| | | ${status} | ${ret}= |Run Keyword And Ignore Error | Iperf3 Udp Rx  | ${dut1} | ${ap_ssid} | ${ap_password} | iperftestlib |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |

### iperf3 TCP RX test
| Test Cases | Action |Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 TCP RX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${test_result}= | Set Variable | PASS |
| | :FOR |${ap_ssid} | ${ap_password} | ${ap_vendor} | ${ap_manu} | IN | @{ap_list}
| | | ${status} | ${ret}= |Run Keyword And Ignore Error | Iperf3 Tcp Rx  | ${dut1} | ${ap_ssid} | ${ap_password} | iperftestlib |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |

### iperf3 UDP TX test
Reboot the device after previous iperf3 RX test due to a bug. We make sure stop tx server every loop.

| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Teardown Iperf3 TX Server |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.iperf3 stop tx server |
| | Teardown Remote | ${endpoint_daemon} | ${testcase} | ${testlib} | ${dut} |

| Test Cases | Action |Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 UDP TX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${test_result}= | Set Variable | PASS |
| | :FOR |${ap_ssid} | ${ap_password} | ${ap_vendor} | ${ap_manu} | IN | @{ap_list}
| | | ${status} | ${ret}= |Run Keyword And Ignore Error | Iperf3 Udp Tx  | ${dut1} | ${ap_ssid} | ${ap_password} | iperftestlib |
| | | Run Keyword | iperftestlib.iperf3 stop tx server |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |

### iperf3 TCP TX test
| Test Cases | Action |Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| iperf3 TCP TX test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | iperftest | iperftestlib |
| | [Teardown] | Teardown Iperf3 TX Server | ${endpoint_daemon} | iperftest | iperftestlib | ${dut1} |
| | ${test_result}= | Set Variable | PASS |
| | :FOR |${ap_ssid} | ${ap_password} | ${ap_vendor} | ${ap_manu} | IN | @{ap_list}
| | | ${status} | ${ret}= |Run Keyword And Ignore Error | Iperf3 Tcp Tx  | ${dut1} | ${ap_ssid} | ${ap_password} | iperftestlib |
| | | Run Keyword | iperftestlib.iperf3 stop tx server |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |




