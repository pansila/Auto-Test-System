import sys
import subprocess
import os
from Test import Test
from mongoengine import connect
import robot
import argparse

# VENV_ROBOT_BIN = "robot.bat"

def run(test):
	robot.run(test.path, outputdir='work_space')
	# work_dir = os.path.dirname(test.path)
	# test_suite = os.path.basename(test.path)

	# command = []
	# command.extend(['pipenv', 'run', 'robot', test_suite])
	# p = subprocess.Popen(command, cwd=work_dir)
	# p.communicate()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('test_suite', type=str, help='specify the test suite to run')
    args = parser.parse_args()

    connect('autotest')

    test = Test.objects(test_suite=args.test_suite)
    if len(test) == 0:
        print('Test suite {} not found in the database'.format(args.test_suite))

    run(test[0])
