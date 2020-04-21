from robotest_utilities.dut import serial_dut

## if only one class is defined, it will be used as the default test library of this module
## if more than one class is defined, please specify which one should be used as test library in the __TEST_LIB__

# __TEST_LIB__ = 'MyTest'

class MyTest(serial_dut):
    def __init__(self, config, task_id):
        super().__init__(config, task_id)

    def hello_world(self, message):
        return message
