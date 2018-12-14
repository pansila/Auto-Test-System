import sys
import subprocess
import os
from Test import Test
from mongoengine import connect

VENV_ROOT = 'D:\\work\\WiFi-test-robot-framework\\robotserver'
VENV_ACTIVATE = "venv\\Scripts\\activate.bat"
VENV_ROBOT_BIN = "robot.bat"

def run(script_file):
	work_dir = os.path.dirname(script_file)
	# work_dir = os.path.abspath(work_dir)
	script_file = os.path.basename(script_file)

	command = ['cmd', '/c']
	command.extend(['cd', work_dir, '&'])
	command.extend([os.path.join(VENV_ROOT, VENV_ACTIVATE), '&'])
	command.extend([VENV_ROBOT_BIN, script_file])
	return subprocess.call(command)

if __name__ == '__main__':
	if len(sys.argv) != 2:
		print('Usage: {} <script file>'.format(sys.argv[0]))
		sys.exit(1)

	test_suite = sys.argv[1]

	connect('autotest')

	test = Test.objects(test_suite=test_suite)
	if len(test) == 0:
		print('Test suite {} not found in the database'.format(test_suite))

	run(test[0].path)
