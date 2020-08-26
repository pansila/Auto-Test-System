import os

class test_utility():
    def __init__(self, daemon_config, task_id):
        self.daemon_config = daemon_config
        self.task_id = task_id

    def get_resource_path_package_data(self):
        return os.path.join(self.daemon_config['resource_dir'], 'package_data', self.__class__.__module__.split('.')[0])

    def get_resource_path_test_data(self):
        return os.path.join(self.daemon_config['resource_dir'], 'test_data')
