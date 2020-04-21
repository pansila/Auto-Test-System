# A Set Of Utilities To Help Design Tests

As of written, the package provides following test libraries to help design tests, the list will grow as the package evolves.

1. serial_dut
   A test library implemented `connect_dut` and `disconnect_dut` interfaces which is wrapper for serial opening and closing.

   There is internal serial read and write interfaces which should be used along with specific serial commands, like `reboot` command for example.

2. download interface
   This is an interface which includes some default download implementations, any test want to have download firmware function should subclass this interface.
   Currently we support downloading firmware by MDK or by J-Link tool

3. logger interface
   This is an interface which provide an unified logger function, it should be used instead of `print` so that the log message of tests will be captured and redirected to the server in realtime.