| Settings | Value | Value | Value | Value | Value |
|---|
| Resource | config.robot |
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | ${endpoint_daemon} |

| Variables | Value |
|---|
| ${dut1} | STA1 |
| ${endpoint_daemon} | EndpointDaemon1 |

| Keywords | Value | Value | Value | Value | Value |
|---|
| Setup Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} |
| | Run Keyword | ${daemon}.start test | ${testcase} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| Teardown Remote |
| | [Arguments] | ${daemon} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${daemon}.stop test | ${testcase} |

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|
| demo test |
| | [Setup] | Setup Remote | ${endpoint_daemon} | demotest | testlib |
| | [Teardown] | Teardown Remote | ${endpoint_daemon} | demotest | testlib | ${dut1} |
| | ${ret} = | testlib.hello world |
| | Should be equal | ${ret} | hello world |
