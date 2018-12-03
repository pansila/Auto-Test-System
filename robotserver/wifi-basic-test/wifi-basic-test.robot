*** Settings ***
Resource                    config.robot
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
    Run Keyword             ${endpoint}.download                        ${dut1}
    Run Keyword             ${endpoint}.Connect Dut                     ${dut1}
    Run Keyword             ${endpoint}.open wifi                       ${dut1}
    Run Keyword             ${endpoint}.scan networks                   ${dut1}
    Run Keyword             ${endpoint}.connect to network              ${dut1}     ${ap_ssid}   ${ap_password}
    ${ret} =                Run Keyword         ${endpoint}.ping        ${dut1}     AP           5
    Should Be Equal         ${ret}              5

*** Keywords ***
Setup Remote
    [Arguments]             ${agent}                ${testcase}
    Run Keyword             ${agent}.start test     ${testcase}

Teardown Remote
    [Arguments]             ${agent}                ${testcase}         ${endpoint}     ${dut}
    Run Keyword             ${endpoint}.Disconnect Dut                  ${dut}
    Run Keyword             ${agent}.stop test                          ${testcase}
***