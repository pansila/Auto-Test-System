import argparse
import os, sys
import subprocess

def run():
    root = os.path.dirname(os.path.realpath(__file__))
    os.chdir(root)
    try:
        subprocess.run('poetry install', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1

    os.chdir(os.path.join(os.path.dirname(root), 'workspace'))
    try:
        ret = subprocess.run('poetry install', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1
    return 0

if __name__ == '__main__':
    sys.exit(run())
