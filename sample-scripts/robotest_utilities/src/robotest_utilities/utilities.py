import os
from ruamel import yaml

class test_utility():
    def __init__(self, daemon_config, task_id):
        self.daemon_config = daemon_config
        self.task_id = task_id
        with open('config.yml', 'r', encoding='utf-8') as f:
            self.config = yaml.load(f, Loader=yaml.RoundTripLoader)

    def get_resource_path_package_data(self):
        return os.path.join(self.daemon_config['resource_dir'], 'package_data', self.__class__.__module__.split('.')[0])

    def get_relative_resource_path_package_data(self):
        return self.get_resource_path_package_data()[len(os.path.abspath(os.curdir)):]

    def get_resource_path_test_data(self):
        return os.path.join(self.daemon_config['resource_dir'], 'test_data')
