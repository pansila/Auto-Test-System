from customtestlibs.device_test import device_test
from customtestlibs.database import TestResult, Test

class demotest(device_test):

    def __init__(self, config):
        super().__init__(config)
        test_result = TestResult()
        test_result.test_case = 'Demo Test'
        test_result.test_suite = Test.objects(test_suite='demo-test').get()
        test_result.test_site = '@'.join((self.config['name'], self.config['location']))
        test_result.tester = 'John'
        test_result.tester_email = 'John@123.com'
        test_result.save()
        self.test_result_id = test_result.pk

    def hello_world(self):
        update = {
            'status': 'Pass',
        }
        TestResult.objects(pk=self.test_result_id).update(**update)
        return 'hello world'
