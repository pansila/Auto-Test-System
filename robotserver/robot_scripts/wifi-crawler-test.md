Note: Install webdriver for selenium before the test, please download [geckodriver](https://github.com/mozilla/geckodriver/releases) and put it in test client's virtual environment executable path.

```
$ pipenv --env
# you may get like C:\Users\abc\.virtualenvs\robotclient-x3F7IyUj, replace the following target with it
cp geckodriver.exe C:\Users\abc\.virtualenvs\robotclient-x3F7IyUj\Scripts
```

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
