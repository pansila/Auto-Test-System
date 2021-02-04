*** Settings ***
Library    Remote    ${remote_daemon_address}    10    WITH NAME    EndpointDaemon1

*** Variables ***
${task_id}                  will be filled by task runner
${endpoint_uid}             will be filled by task runner
${address_daemon}           127.0.0.1
${port_daemon}              8270
${remote_daemon_address}    http://${address_daemon}:${port_daemon}/${endpoint_uid}

*** Keywords ***
Setup Remote
    [Arguments]
    Run Keyword        EndpointDaemon1.start test        ${TEST NAME}                                ${task_id}
Load And Import Library
    [Arguments]        ${backing file}                   ${_}                                        ${testlib}
    Run Keyword        EndpointDaemon1.load library      ${backing file}
    Import Library     Remote                            ${remote_daemon_address}/${backing file}    WITH NAME           ${testlib}
Teardown Remote
    [Arguments]        ${backing file}
    Run Keyword        EndpointDaemon1.stop test         ${backing file}                             ${TEST STATUS}
