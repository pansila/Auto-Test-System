*** Settings ***
Library    Remote    ${remote_daemon_address}    10    WITH NAME    EndpointDaemon1

*** Variables ***
${task_id}                  will be automatically filled by task runner
${address_daemon}           127.0.0.1
${port_daemon}              8270
${port_test}                8271
${remote_daemon_address}    http://${address_daemon}:${port_daemon}
${remote_test_address}      http://${address_daemon}:${port_test}

*** Keywords ***
Setup Remote
    [Arguments]    ${backing file}    ${testlib}
    Run Keyword    EndpointDaemon1.start test    ${TEST NAME}   ${backing file}     ${task_id}
    Import Library    Remote    ${remote_test_address}    WITH NAME    ${testlib}
Teardown Remote
    [Arguments]
    Run Keyword    EndpointDaemon1.stop test    ${TEST NAME}    ${TEST STATUS}