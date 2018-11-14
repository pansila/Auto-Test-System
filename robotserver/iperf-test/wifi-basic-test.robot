*** Settings ***
Library                 DebugLibrary
Library                 Remote    http://${ADDRESS_AGENT1}:${PORT_AGENT}     10    WITH NAME   EndpointAgent1
Resource                mykeywords.robot

*** Variables ***
${ADDRESS_AGENT1}       127.0.0.1
${PORT_AGENT}           8270
${PORT_TEST}            8271

*** Test Cases ***
Set up the test
    EndpointAgent1.start                        ${testcase}

Ping test
    Import Library          Remote              http://${ADDRESS_AGENT1}:${PORT_TEST}     WITH NAME   Endpoint1
    Endpoint1.Connect Dut                       ${STA1}
    Endpoint1.open wifi                         ${STA1}
    Endpoint1.scan networks                     ${STA1}
    Endpoint1.connect to network                ${STA1}     tplink886   12345678
    ${ret} =              Endpoint1.ping        ${STA1}     AP          1
    Should Be Equal       ${ret}                1
    ${ret} =              Endpoint1.ping        ${STA1}     testbox1    1
    Should Be Equal       ${ret}                1
    Endpoint1.Disconnect Dut                    ${STA1}
    EndpointAgent1.stop                         ${testcase}
***
iperf test as UDP TX
    connect to dut device    STA1
    open wifi
    scan networks
    connect to network       tplink886    12345678
    ping                     AP           5
    ping                     testbox1     5
    start traffic            SEND         UDP       10M     1500
    Status Should Be         NO EARLY STOP

wifi enable/disable test
    connect to dut device    STA1
    :FOR    ${var}    in     @{VALUE}
    \       Log       ${var}
    open wifi
    scan networks
    connect to network       tplink886 12345678
    ping                     AP 5
    ping                     testbox1 5
    close wifi

wifi password test
    connect to dut device    STA1
    open wifi
    scan networks
    connect to network    tplink886     1212
    ping                  AP            100
    ping                  testbox1      100
    Status Should Be      PING PASS