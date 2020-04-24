# A Sample Test Package To Run Basic Tests For A WiFi device

This is a sample implementation of WiFi DUT for basic WiFi tests. All custom WiFi DUTs should subclass the `base_wifi_dut` and override the interfaces to perform the tests defined in the markdown tests.

The sample class `base_wifi_dut` is a sub class of `serial_dut`, so it inherits the `connect_dut`, `disconnect_dut` and other serial manipulating interfaces, you can re-use them in your classes.

Sample code:
```python
class esp8266_dut(base_wifi_dut, download_fw_intf):
	def __init__(self, daemon_config, task_id):
		super().__init__(daemon_config, task_id)
		...

	def open_wifi(self, dutName):
		...
```
The argument `daemon_config` holds the test endpoint's specific configurations, like `server_url`, etc. It will be used by `server_api`, usually you don't need to care about it.

The argument `task_id` is the test task's id which is the token to communicate with the server, usually you don't need to care about it.

These tow arguments should be passed to super class as it-is.

## The interface List
1. open_wifi
   Open/Enable the WiFi function on the DUT, most wifi devices have it enabled by default after boot-up.
2. close_wifi
   Close/Disable the WiFi function.
3. scan_networks
   Scan the networks
4. connect_to_network
   Connect to a specified network with provided credentials
5. disconnect_network
   Disconnect the network
6. create_softap
   Create/Set up the SoftAP function on the DUT

## The implemented tests in the markdown scripts:
1. ping test
2. iperf2 UDP TX test
3. iperf2 UDP RX test
4. iperf2 TCP TX test
5. iperf2 TCP RX test
6. iperf3 UDP TX test
7. iperf3 UDP RX test
8. iperf3 TCP TX test
9. iperf3 TCP RX test