# A Set Of Utilities To Help Design Tests

As of written, the package provides following test libraries to help design tests, the list will grow as the package evolves.

1. serial_dut

   A test library implemented `connect_dut` and `disconnect_dut` interfaces which are just wrappers for serial opening and closing.

   We provide a pair of serial read and write interfaces which can be used to perform specific serial commands, like `reboot` command for example.
   
   You can put your DUT's configurations in the `config.yml` which is under the DUT endpoint's `workspace` directory.

   Here is the sample code to define your custom DUT tests, more details please refer to `wifi_base_test` test package and other more complicated test packages.
   ```python
   class wifi_basic_test(serial_dut):
      def __init__(self, daemon_config, task_id):
		   super().__init__(daemon_config, task_id)
		   ...

	   def dut_open_wifi(self, dutName):
		   ...

   ```
   The argument `daemon_config` holds the test endpoint's specific configurations, like `server_url`, etc. It will be used by `server_api`, usually you don't need to care about it.

   The argument `task_id` is the test task's id which is the token to communicate with the server, usually you don't need to care about it.

   These tow arguments should be passed to super class as it is.

2. download interface

   This is an interface which includes some default download implementations, any test want to have download firmware feature should subclass this interface.
   Currently we support downloading firmware by MDK and J-Link.

   The firmware to be programmed to the DUT will be first fetched from the server via the test resource API, and then saved to the `resources` directory under the DUT endpoint's `workspace` directory.

3. wifi_dut
   This is a prototype class definition of the WiFi DUT for basic WiFi tests. All custom WiFi DUTs should subclass the `wifi_dut_base` and override the interfaces to perform the tests defined in the markdown tests.

   The prototype class `wifi_dut_base` is a sub class of `serial_dut`, so it inherits the `connect_dut`, `disconnect_dut` and other serial manipulating interfaces, you can re-use them in your classes.

   Sample code:
   ```python
   class esp8266_dut(wifi_dut_base, download_fw_intf):
   	def __init__(self, daemon_config, task_id):
   		super().__init__(daemon_config, task_id)
   		...

   	def open_wifi(self, dutName):
   		...
   ```
   The argument `daemon_config` holds the test endpoint's specific configurations, like `server_url`, etc. It will be used by `server_api`, usually you don't need to care about them.
   The argument `task_id` is the test task's ID which is the token to communicate with the server, usually you don't need to care about it.

   These two arguments should be passed to super class as it-is.

   ## The interface List
   1. dut_open_wifi
      Open/Enable the WiFi function on the DUT, most wifi devices have it enabled by default after boot-up.
   2. dut_close_wifi
      Close/Disable the WiFi function.
   3. dut_scan_networks
      Scan the networks
   4. dut_connect_to_network
      Connect to a specified network with provided credentials
   5. dut_disconnect_network
      Disconnect the network
   6. dut_set_channel
      Set a WiFi channel of the DUT
   7. dut_create_softap
      Create/Set up the SoftAP function on the DUT
   8. dut_reboot
      Reboot the DUT

4. logger interface

   This is an interface which provide an unified logger function, it should be used instead of `print` so that the log message of tests will be captured and redirected to the server in realtime.
