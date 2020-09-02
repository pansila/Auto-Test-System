import argparse
import os
import subprocess
import sys


def run():
    root = os.path.dirname(os.path.realpath(__file__))
    os.chdir(root)
    try:
        subprocess.run('poetry install', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1

    os.chdir(os.path.join(os.path.dirname(root), 'workspace'))
    executable = subprocess.check_output('py -3-32 -c "import sys; print(sys.executable)"', shell=True, universal_newlines=True)
    try:
        ret = subprocess.run('poetry env use ' + executable, shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1
    try:
        ret = subprocess.run('poetry install', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1
    return 0

if __name__ == '__main__':
    sys.exit(run())
