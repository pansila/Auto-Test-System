*** Settings ***
Resource                    config-keywords.robot
Library                     DebugLibrary
Library                     Remote          ${remote_agent_address}   10    WITH NAME   ${endpoint_agent}

*** Variables ***
${dut1}                     STA1
${dut2}                     STA2
${endpoint_agent}           EndpointAgent1
${endpoint}                 Endpoint1
${ap_ssid}                  tplink886
${ap_password}              12345678

*** Test Cases ***
Ping test
    [Setup]                 Setup Remote        ${endpoint_agent}       pingtest
    [Teardown]              Teardown Remote     ${endpoint_agent}       pingtest    ${endpoint}  ${dut1}
    Import Library          Remote              ${remote_test_address}  WITH NAME   ${endpoint}
    Run Keyword             ${endpoint}.Connect Dut                     ${dut1}
    Run Keyword             ${endpoint}.open wifi                       ${dut1}
    Run Keyword             ${endpoint}.scan networks                   ${dut1}
    Run Keyword             ${endpoint}.connect to network              ${dut1}     ${ap_ssid}   ${ap_password}
    ${ret} =                Run Keyword         ${endpoint}.ping        ${dut1}     AP           5
    Should Be Equal         ${ret}              5
    Run Keyword             ${endpoint}.Disconnect Dut                  ${dut1}

*** Keywords ***
Setup Remote
    [Arguments]             ${agent}            ${testcase}
    Run Keyword             ${agent}.start      ${testcase}

Teardown Remote
    [Arguments]             ${agent}            ${testcase}             ${endpoint}     ${dut}
    Run Keyword             ${agent}.stop                               ${testcase}
    Run Keyword             ${endpoint}.Disconnect Dut                  ${dut}

***
iperf test as UDP TX
    connect to dut device    dut1
    open wifi
    scan networks
    connect to network       tplink886    12345678
    ping                     AP           5
    ping                     testbox1     5
    start traffic            SEND         UDP       10M     1500
    Status Should Be         NO EARLY STOP

wifi enable/disable test
    connect to dut device    dut1
    :FOR    ${var}    in     @{VALUE}
    \       Log       ${var}
    open wifi
    scan networks
    connect to network       tplink886 12345678
    ping                     AP 5
    ping                     testbox1 5
    close wifi

wifi password test
    connect to dut device    dut1
    open wifi
    scan networks
    connect to network    tplink886     1212
    ping                  AP            100
    ping                  testbox1      100
    Status Should Be      PING PASS