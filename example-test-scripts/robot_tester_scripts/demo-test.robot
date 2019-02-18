*** Settings ***
Resource    config.robot
Library    Remote    ${remote_daemon_address}    10    WITH NAME    ${endpoint_daemon}

*** Variables ***

${dut1}              STA1
${endpoint_daemon}    EndpointDaemon1

*** Keywords ***
Setup Remote
    [Arguments]    ${daemon}    ${testcase}    ${testlib}
    Run Keyword    ${daemon}.start test    ${testcase}
    Import Library    Remote    ${remote_test_address}    WITH NAME    ${testlib}
Teardown Remote
    [Arguments]    ${daemon}    ${testcase}    ${testlib}    ${dut}
    Run Keyword    ${daemon}.stop test    ${testcase}

*** Test Cases ***
hello world
    [Setup]    Setup Remote    ${endpoint_daemon}    demotest    testlib
    [Teardown]    Teardown Remote    ${endpoint_daemon}    demotest    testlib    ${dut1}
    ${ret} =    testlib.hello world
    Should be equal    ${ret}    hello world
