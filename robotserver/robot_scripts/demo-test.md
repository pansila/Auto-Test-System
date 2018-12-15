This is a demo test, it demonstrates the potential to run a robot test in a markdown file.

### Setup for all test cases
| Settings | Value | Value | Value | Value | Value |
|---|
| Resource | config.robot |
| Library | Remote | ${remote_agent_address} | 10 | WITH NAME | ${endpoint_agent} |

| Variables | Value |
|---|
| ${dut1} | STA1 |
| ${endpoint_agent} | EndpointAgent1 |

| Keywords | Value | Value | Value | Value | Value |
|---|
| Setup Remote |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} |
| | Run Keyword | ${agent}.start test | ${testcase} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| Teardown Remote |
| | [Arguments] | ${agent} | ${testcase} | ${testlib} | ${dut} |
| | Run Keyword | ${agent}.stop test | ${testcase} |

### Demo Test

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|
| demo test |
| | [Setup] | Setup Remote | ${endpoint_agent} | demotest | testlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | demotest | testlib | ${dut1} |
| | ${ret} = | testlib.hello world |
| | Should be equal | ${ret} | hello world |
