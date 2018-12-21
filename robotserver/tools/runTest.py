import sys
import subprocess
import os
from Test import Test
from mongoengine import connect
import robot
import argparse
import time

sys.path.append('robot_python_scripts')
from customtestlibs.database import Test, Task, TaskQueue

def listen_task():
    print('Start listening tasks from database 127.0.0.1:27017')
    print(TaskQueue.objects())
    while True:
        task = TaskQueue.pop('192.168.3.100:8270')
        if task != None:
            args = ['--outputdir', 'work_space', task.path]
            robot.run_cli(args)
        print('Task is none')
        time.sleep(1)

if __name__ == '__main__':
    connect('autotest')

    if len(sys.argv) < 2:
        listen_task()
        sys.exit(0)

    # if len(os.getcwd().split(os.path.sep)) < 2:
    #     print('Please run it in the server root directory')
    #     sys.exit(1)

    test_suite = sys.argv[1]

    try:
        test = Test.objects(test_suite=test_suite).get()
    except Test.DoesNotExist:
        print('Test suite {} not found in the database'.format(test_suite))
        print('Usage: {} <test_suite> [options]'.format(sys.argv[0]))
        sys.exit(1)
    except Test.MultipleObjectsReturned:
        print('Multiple Test suite {} found in the database'.format(test_suite))
        sys.exit(1)

    args = ['--outputdir', 'work_space', *sys.argv[2:], test.path]
    ret = robot.run_cli(args)
    sys.exit(ret)
