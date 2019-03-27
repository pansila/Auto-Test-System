This is a demo test, it demonstrates the potential to run a robot test in a markdown file.

### Setup for all test cases
| Settings | Value | Value | Value | Value | Value |
|---| ---|---|---|---|---|
| Library | Remote | ${remote_daemon_address} | 10 | WITH NAME | EndpointDaemon1 |

| Variables | Value |
|---|---|
| ${task_id} | will be automatically filled by task runner |
| ${address_daemon} | 127.0.0.1 |
| ${port_daemon} | 8270 |
| ${port_test} | 8271 |
| ${remote_daemon_address} | http://${address_daemon}:${port_daemon} |
| ${remote_test_address} | http://${address_daemon}:${port_test} |
| ${echo_message} | goodbye |

| Keywords | Value | Value | Value | Value | Value |
|---| ---|---|---|---|---|
| Setup Remote |
| | [Arguments] | ${daemon} | ${backing file} | ${testlib} |
| | Run Keyword | ${daemon}.start test | ${TEST NAME} | ${backing file} | ${task_id} |
| | Import Library | Remote | ${remote_test_address} | WITH NAME | ${testlib} |
| Teardown Remote |
| | [Arguments] | ${daemon} |
| | Run Keyword | ${daemon}.stop test | ${TEST NAME} | ${TEST STATUS} |

### Demo Test

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
|---|---|---|---|---|---|---|
| hello world |
| | [Setup] | Setup Remote | EndpointDaemon1 | demotest.py | testlib |
| | [Teardown] | Teardown Remote | EndpointDaemon1 |
| | ${ret} = | testlib.hello world | ${echo_message} |
| | Should be equal | ${ret} | ${echo_message} |
