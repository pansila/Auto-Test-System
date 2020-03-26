from customtestlibs.device_test import device_test

class demotest(device_test):

    def __init__(self, config, task_id):
        super().__init__(config, task_id)

    def hello_world(self, message):
        return message
