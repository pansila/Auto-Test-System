import sys
import subprocess
import os
from Test import Test
from mongoengine import connect
import robot
import argparse

# VENV_ROBOT_BIN = "robot.bat"

def run(test, args):
	robot.run(test.path, *args, outputdir='work_space')
	# work_dir = os.path.dirname(test.path)
	# test_suite = os.path.basename(test.path)

	# command = []
	# command.extend(['pipenv', 'run', 'robot', test_suite])
	# p = subprocess.Popen(command, cwd=work_dir)
	# p.communicate()

if __name__ == '__main__':
    notFound = False
    parser = argparse.ArgumentParser()
    parser.add_argument('test_suite', nargs='+', type=str, help='specify the test suite to run')
    args = parser.parse_args()

    connect('autotest')

    [test_suite, *robot_args] = args.test_suite

    try:
        test = Test.objects(test_suite=test_suite)
    except IndexError:
        notFound = True

    if notFound or len(test) == 0:
        print('Test suite {} not found in the database'.format(test_suite))
        sys.exit(1)

    run(test[0], robot_args)
