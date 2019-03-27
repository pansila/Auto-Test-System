*** Settings ***
Library    Remote    ${remote_daemon_address}    10    WITH NAME    EndpointDaemon1

*** Variables ***

${address_daemon}           127.0.0.1
${port_daemon}              8270
${port_test}                8271
${remote_daemon_address}    http://${address_daemon}:${port_daemon}
${remote_test_address}      http://${address_daemon}:${port_test}
${message}                  goodbye

*** Keywords ***
Setup Remote
    [Arguments]    ${daemon}    ${backing file}    ${testlib}
    Run Keyword    ${daemon}.start test    ${TEST NAME}   ${backing file}
    Import Library    Remote    ${remote_test_address}    WITH NAME    ${testlib}
Teardown Remote
    [Arguments]    ${daemon}
    Run Keyword    ${daemon}.stop test    ${TEST NAME}    ${TEST STATUS}

*** Test Cases ***
hello world
    [Setup]    Setup Remote    EndpointDaemon1    demotest.py    testlib
    [Teardown]    Teardown Remote    EndpointDaemon1
    ${ret} =    testlib.hello world  ${message}
    Should be equal    ${ret}    ${message}
