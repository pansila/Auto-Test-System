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
| | Run Keyword | ${testlib}.close |
| | Run Keyword | ${agent}.stop test | ${testcase} |

### Crawler test

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|
| crawler test |
| | [Setup] | Setup Remote | ${endpoint_agent} | crawlertest | testlib |
| | [Teardown] | Teardown Remote | ${endpoint_agent} | crawlertest | testlib | ${dut1} |
| | testlib.login |
