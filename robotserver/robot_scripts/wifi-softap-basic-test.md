- [SoftAP basic Test](#softap-basic-test)
- [Test Plans](#test-plans)
	- [Setup for all test cases](#setup-for-all-test-cases)
	- [SoftAP Security Test](#softap-security-test)
	- [SoftAP Open Test](#softap-open-test)
	- [SoftAP Hidden Test](#softap-hidden-test)
	- [SoftAP Specific SSID Test](#softap-specific-ssid-test)
	- [SoftAP Specific Password Test](#softap-specific-password-test)
	- [SoftAP Channel Test](#softap-channel-test)
## SoftAP basic Test
DUT creates a SoftAP with permutations of different SSIDs, channels and credentials. After network of SoftAP is ready, SUT will connect to it and make a connection availability test.

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
| #AP LIST | SSID| PASSWORD | CHANNEL | HIDDEN |
| @{ap_security}| ft2019_sec | 12345678 | 1 | 0 |
| @{ap_open} | ft2019_open |  |  |  |
| @{ap_specific_ssid} | ~!#$%^&*()@_+\"><:;,@./\\[]{?},0 | ~!#$%^&*()@_+\"><:;,@./\\[]{? | 3 | 0 |
| @{ap_specific_pwd}  | ft2019_abcd@#$$# | ~!#$%^&*()@_+\"><:;,@./\\[]{?},0~!#$%^&*()@_+\"><:;,@./\\[]{?},0 | 3 | 0 |
| @{ap_hidden} | ft2019_hidden | 12345678 | 6 | 1 |
| @{ap_channels} | ft2019_channel1 | 12345678 | 1 | 0 |
| ... | ft2019_channel6 | 12345678 | 6 | 0 |
| ... | ft2019_channel11 | 12345678 | 11 | 0 |
| ... | ft2019_channel13 | 12345678 | 13 | 0 |


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


### SoftAP Security Test
DUT Create a security SoftAP with WPA2/AES. Then PC station connect the SoftAP. Finnally, DUT do ping test with the station.
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| SoftAP Security |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | pingtestlib.download | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | pingtestlib | @{ap_security}[0] | @{ap_security}[1] | @{ap_security}[2] | @{ap_security}[3] |
| | ${ret} = | pingtestlib.ping | ${dut1} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |

### SoftAP Open Test
DUT Create a open SoftAP. Then PC station connect the SoftAP. Finnally, DUT do ping test with the station.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| SoftAP Open |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | pingtestlib | @{ap_open}[0] | ${EMPTY} | ${EMPTY} | ${EMPTY} |
| | ${ret} = | pingtestlib.ping | ${dut1} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |

### SoftAP Hidden Test
DUT Create a hidden security SoftAP with WPA2/AES. Then PC station connect the SoftAP. Finnally, DUT do ping test with the station.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| SoftAP Hidden |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | pingtestlib | @{ap_hidden}[0] | @{ap_hidden}[1] | @{ap_hidden}[2] | @{ap_hidden}[3] |
| | ${ret} = | pingtestlib.ping | ${dut1} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |

### SoftAP Specific SSID Test
Boundary test SoftAP's SSID. DUT Create a security SoftAP that SSID's length is 32 and name is special characters. Then PC station connect the SoftAP. Finnally, DUT do ping test with the station.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| SoftAP Specific SSID  |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | pingtestlib | @{ap_specific_ssid}[0] | @{ap_specific_ssid}[1] | @{ap_specific_ssid}[2] | @{ap_specific_ssid}[3] |
| | ${ret} = | pingtestlib.ping | ${dut1} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |

### SoftAP Specific Password Test
Boundary test SoftAP's password. DUT Create a security SoftAP that Password's length is 64 and uses special characters. Then PC station connect the SoftAP. Finnally, DUT do ping test with the station.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|
| SoftAP Specific Password  |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | ${dut_ip} | ${sta_ip} = | Create Network | ${dut1} | pingtestlib | @{ap_specific_pwd}[0] | @{ap_specific_pwd}[1] | @{ap_specific_pwd}[2] | @{ap_specific_pwd}[3] |
| | ${ret} = | pingtestlib.ping | ${dut1} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |

### SoftAP Channel Test
Dut select channel 1, 6, 11, 13 to test. For each channel, DUT create a security SoftAP with WPA2/AES. Then PC station connect the softap. Finnally, DUT do ping test with the station.
| Keywords | Value | Value | Value | Value | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|---|---|---|---|
| Test Channel |
| | [Arguments] | ${dut} | ${testlib} | ${ssid} | ${passwd} | ${channel} | ${hidden} |
| | ${dut_ip} | ${sta_ip} = | Run Keyword | Create Network | ${dut1} | ${testlib} | ${ssid} | ${passwd} | ${channel} | ${hidden} |
| | ${ret} = | Run Keyword |${testlib}.ping | ${dut} | ${sta_ip} | 5 |
| | Should Be True | ${ret} >= 4 |
| | [Return] | ${ret} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SoftAP Channels |
| | [Setup] | Setup Remote | ${endpoint_daemon} | pingtest | pingtestlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | pingtest | pingtestlib | ${dut1} |
| | ${test_result}= | Set Variable | PASS |
| | :FOR | ${ap_ssid} | ${ap_password} | ${ap_channel} | ${ap_hidden} | IN | @{ap_channels}
| | | ${status} | ${ret} = | Run Keyword And Ignore Error | Test Channel | ${dut1} | pingtestlib | ${ap_ssid} | ${ap_password}|  ${ap_channel} | ${ap_hidden} |
| | | Set Test Documentation | SoftAP Channels Test  for channel *${ap_channel}* Result *${status}* \n\n| append=True |
| | | ${test_result}= | Set Variable If | '${status}' == 'FAIL' | FAIL| ${test_result}|
| | Should Be True| '${test_result}' == 'PASS' |