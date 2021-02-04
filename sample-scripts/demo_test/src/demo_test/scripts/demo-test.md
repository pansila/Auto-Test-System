# This test demonstrates that how you can run a robot test in a markdown file.

### Every test data file needs to include the `setup.robot`
| Settings | Value |
| -------- | ----- |
| Resource | setup.robot |

| Variables | Value | Value |
| --------- | ----- | ----- |
| ${echo_message} | goodbye |  |
| ${asdfasdf} | goodbye |  |
| @{test_list} | asdf | asdfa |
| ... | wsesdf | sdfsdf |
| &{test_dict} | asdf=1231 | asdfa=12312 |
| ... | sdfsdf=11111 | sdfssdf=12312 |

| Keywords | Value | Value | Value | Value | Value |
| -------- | ----- | ----- | ----- | ----- | ----- |
| Setup Test |
|  | [Arguments] | ${backing file} | ${testlib} |
|  | Setup Remote |
|  | Load And Import Library | ${backing file} | WITH NAME | ${testlib} |
| Teardown Test |
|  | [Arguments] | ${backing file} | ${testlib} |
|  | Teardown Remote | ${backing file} |

### Every test case needs to include `Setup` and `Teardown` sections which ensure to import the test and start and stop it properly

Keyword `Setup Remote` is introduced by `setup.robot`. It takes two arguments, the first one is the execution script that runs on the test endpoint, the second one is the test library alias which is used hereafter to call its keywords.

Keyword `Teardown Remote` is also introduced by `setup.robot`. It closes the test with some necessary work in the background.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
| ---------- | ------ | -------- | -------- | -------- | -------- | -------- |
| hello world |  |
|  | [Setup] | Setup Test | demo_test/demotest.py | testlib |
|  | [Teardown] | Teardown Test | demo_test/demotest.py | testlib |
|  | ${ret} = | testlib.hello world | ${echo_message} |
|  | Should be equal | ${ret} | ${echo_message} |