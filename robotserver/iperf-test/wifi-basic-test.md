## Notes of writing a test script
Since it's a distributed test system as opposed to a local test system, some essential configurations need to be included in the test script as follows.
* Include "Library Remote <address:port>" to connect to an endpoint
* Include the dynamic "Import Library <address:port>" to connect to the test library for the downloaded test case

## Basic WiFi test
* Ping Test
* WiFi Enable/Disable Test
* Connect/Disconnect Test
* WiFi Password Test
* Iperf TCP TX test
* Iperf TCP RX test
* Iperf UDP TX test
* Iperf UDP RX test

```robotframework
*** Settings ***
Library                 Remote    http://${ADDRESS1}:${PORT1}     10    WITH NAME   EndpointAgent1
Resource                mykeywords.robot

*** Variables ***
${ADDRESS1}    127.0.0.1
${PORT1}       8270
${PORT2}       8271

*** Test Cases ***
Set up the test
    EndpointAgent1.start                     ${testcase}

Ping test
    Import Library          Remote      http://${ADDRESS1}:${PORT2}     WITH NAME   Endpoint1
    Endpoint1.Connect To Dut Device     ${STA1}
    Endpoint1.open wifi                 ${STA1}
    Endpoint1.scan networks
    Endpoint1.connect to network    tplink886     \
    ${ret} =              Endpoint1.ping          AP            100
    Should Be Equal       ${ret}        100
    ${ret} =              Endpoint1.ping          testbox1      100
    Should Be Equal       ${ret}        100
```