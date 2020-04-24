# This test demonstrates how you can run a robot test in a markdown file.

There are two ways to support a test suite in the markdown file.

1. Write the robot test case in the markdown code block.

````
```robotframework
*** Settings ***
Documentation    Example using the space separated plain text format.
Library          OperatingSystem

*** Variables ***
${MESSAGE}       Hello, world!

*** Test Cases ***
My Test
    [Documentation]    Example test
    Log    ${MESSAGE}
    My Keyword    /tmp
``` 
````

2. Write the robot test case in the markdown table.
It's the recommended way to write our test cases as it's more legible for test writer. Here is the markdown way to write the test code for the `demo test`.
---
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

### Every test case needs to include `Setup` and `Teardown` sections which ensure to import the test and start and stop it properly

Keyword `Setup Remote` is introduced by `setup.robot`. It takes two arguments, the first one is the execution script that runs on the test endpoint, the second one is the test library alias which is used hereafter to call its keywords.

Keyword `Teardown Remote` is also introduced by `setup.robot`. It closes the test with some necessary work in the background.

| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
| ---------- | ------ | -------- | -------- | -------- | -------- | -------- |
| hello world |  |  |  |  |  |  |
|  | [Setup] | Setup Remote | demo_test/demotest.py | testlib |  |  |
|  | [Teardown] | Teardown Remote |  |  |  |  |
|  | ${ret} = | testlib.hello world | ${echo_message} |  |  |  |
|  | Should be equal | ${ret} | ${echo_message} |  |  |  |