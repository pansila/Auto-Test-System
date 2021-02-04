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
| Setup Test |
|  | [Arguments] | ${backing file} | ${testlib} | ${dut} |
|  | Setup Remote |
|  | Load And Import Library | ${backing file} | WITH NAME | ${testlib} |
|  | Run Keyword | ${testlib}.connect | ${dut} |
| Teardown Test |
|  | [Arguments] | ${backing file} | ${testlib} | ${dut} |
|  | Run Keyword | ${testlib}.disconnect | ${dut} |
|  | Teardown Remote | ${backing file} |

### Every test case needs to include `Setup` and `Teardown` sections which ensure to import the test and start and stop it properly
| Test Cases | Action | Argument | Argument | Argument | Argument | Argument |
| ---------- | ------ | -------- | -------- | -------- | -------- | -------- |
| hello world |  |  |  |  |  |  |
|  | [Setup] | Setup Test | ${backing file} | testlib | ${dut1} |
|  | [Teardown] | Teardown Test | ${backing file} | testlib | ${dut1} |
|  | LOG | hello world |
