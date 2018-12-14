import sys
import subprocess
import os
from Test import Test
from mongoengine import connect
import robot

VENV_ROBOT_BIN = "robot.bat"

def run(test):
	work_dir = os.path.dirname(test.path)
	# work_dir = os.path.abspath(work_dir)
	test_suite = os.path.basename(test.path)

	robot.run(test.path)
	# command = []
	# command.extend(['pipenv', 'run', 'robot', test_suite])
	# p = subprocess.Popen(command, cwd=work_dir)
	# p.communicate()

if __name__ == '__main__':
	if len(sys.argv) != 2:
		print('Usage: {} <test suite name>'.format(sys.argv[0]))
		sys.exit(1)

	test_suite = sys.argv[1]

	connect('autotest')

	test = Test.objects(test_suite=test_suite)
	if len(test) == 0:
		print('Test suite {} not found in the database'.format(test_suite))

	run(test[0])
