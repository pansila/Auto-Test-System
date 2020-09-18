# This test demonstrates how you can manipulate the DUT with a serial interface

### Every test data file needs to include the `setup.robot`
| Settings | Value |
| -------- | ----- |
| Resource | setup.robot |

### Set up custom `Setup` and `Teardown` keywords and other initialization work
| Variables | Value |
|---|---|
| ${dut1} | STA1 |
| ${backing file} | robotest_utilities/dut/devices.py |

| Keywords | Value | Value | Value | Value | Value |
|---|---|---|---|---|---|
| Setup DUT |
| | [Arguments] | ${backing file} | ${testlib} | ${dut} |
| | Setup Remote | ${backing file} | ${testlib} |
| | Run Keyword | ${testlib}.Connect Dut | ${dut} |
| Teardown DUT |
| | [Arguments] | ${testlib} | ${dut} |
| | Run Keyword | ${testlib}.Disconnect Dut | ${dut} |
| | Teardown Remote |

### Every test case needs to include `Setup` and `Teardown` sections which ensure to import the test and start and stop it properly
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
| ---------- | ------ | -------- | -------- | -------- | -------- | -------- |
| hello world |  |  |  |  |  |  |
|  | [Setup] | Setup DUT | ${backing file} | testlib | ${dut1} |  |
|  | [Teardown] | Teardown DUT |  |  |  |  |
|  |  | testlib.reboot |  |  |  |  |
