
## Compatibility Test Plan
We take many APs include different vendor, different manufacturer, different model to do compatibility testing.
These APs listed in the ap list, you can easy add new AP to the list or delete one from it follow the format.
For each AP in the list, DUT would first do scan, and then connect it, finanlly do ping test.
If all of actions is executed successfully, we suppose the DUT compat the AP.

We use ping test lib do Compatibility test.

TODO: Wireless mode test and wireless security test

## Setup for all test cases

| Settings | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Resource | config.robot |
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | ${endpoint_daemon} |

| Variables | Value | Value | Value | Value |
|---|---| ---| ---| ---|
| ${dut1} | STA1 |
| ${dut2} | STA2 |
| ${endpoint_daemon} | EndpointDaemon1 |
| ${test_result} | PASS |
|#AP LIST | SSID| PASSWORD | VENDOR | MANUFACTURER |
| @{ap_list}| ASUS | 12345678 | MTK | ASUS |
| ... | huawei851 | 12345678 | RealTeK | HUAWEI |
| ... | 360wifi | 12345678 | RealTeK | NETCORE |
| ... | tenda_ac15 | 12345678 | BCM | TENDA |
| ... | test_11n |  | Qualcomm | TP-LINK |


| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Setup Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} |
| | Run Keyword | ${daemon}.start test | ${testcase} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut1} |
| Teardown Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Run Keyword | ${daemon}.stop test | ${testcase} |
| Connect and Ping AP |
| | [Arguments] | ${dut} | ${ssid} | ${pwd} | ${testlib} |
| | Run Keyword | ${testlib}.scan networks | ${dut} |
| | Run Keyword | ${testlib}.connect to network | ${dut} | ${ssid} | ${pwd} |
| | ${ret} = | Run Keyword | ${testlib}.ping | ${dut} | AP | 5 |
| | Run Keyword | ${testlib}.disconnect network | ${dut} |
| | Should Be True | ${ret} >= 4 |
| | [Return] |  ${ret} |



| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| Compatibility Test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | pingtestlib.download | ${dut1} |
| | pingtestlib.open wifi | ${dut1} |
| | :FOR |${ap_ssid} | ${ap_password} | ${ap_vendor} | ${ap_manu} | IN | @{ap_list}
| | | ${status} | ${ret}= |Run Keyword And Ignore Error | Connect and Ping AP | ${dut1} | ${ap_ssid} | ${ap_password} | pingtestlib |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |