import re
from customtestlibs.wifi_test import wifi_basic_test
from customtestlibs.routers import huawei

class crawlertest(wifi_basic_test):

    def __init__(self, config, vendor, product):
        super().__init__(config)
        if vendor.upper() == 'HUAWEI':
            if product.upper() == 'HUAWEI851':
                self.crawler = huawei.huawei851()
        else:
            raise AssertionError('Vendor {} : product {} is not supported'.format(vendor, product))

    def login(self):
        print('login test')
        self.crawler.login()

    def close(self):
        self.crawler.close()
        self.crawler = None
