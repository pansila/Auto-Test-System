import sys
import subprocess
import os
from Test import Test
from mongoengine import connect
import robot
import argparse

sys.path.append('robot_python_scripts')
from customtestlibs.database import Test

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Need to specify a test suite to run')
        sys.exit(1)
    # if len(os.getcwd().split(os.path.sep)) < 2:
    #     print('Please run it in the server root directory')
    #     sys.exit(1)

    connect('autotest')

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
