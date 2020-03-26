import os, sys
import subprocess
import re
from pathlib import Path
from io import StringIO

# https://github.com/techtonik/python-patch/
# with patch
# https://storage.googleapis.com/google-code-attachments/python-patch/issue-28/comment-2/patch-support-new-files-20141214.diff
import patch


# 7-bit C1 ANSI sequences
ansi_escape = re.compile(r'''
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
''', re.VERBOSE)

venv = None
try:
    lines = subprocess.check_output('poetry env info', shell=True).decode()
except subprocess.CalledProcessError:
    print('poetry not found, please add it to the environment variable PATH')
    sys.exit(1)

for line in StringIO(lines):
    parts = line.partition(':')
    parts = [ansi_escape.sub('', p) for p in parts]
    if parts[0] == 'Path':
        venv = parts[2].strip()
        break
else:
    print('No virtual environment found')
    sys.exit(1)

if os.name == 'nt':
    venv =  Path(venv) / 'Lib'
elif os.name == 'posix':
    venv =  Path(venv) / 'lib' / 'python{}.{}'.format(sys.version_info.major, sys.version_info.minor)
else:
    print('Unknown OS {}'.format(os.name))
    sys.exit(1)

patchdir = os.path.dirname(os.path.abspath(__file__))
patchset = patch.fromfile(Path(patchdir) / 'robot.diff')
try:
    ret = patchset.apply(root=venv)
    # ret = patchset.revert(root=venv)
    if not ret:
        print('Patching failed')
        raise AssertionError()
except:
    print(sys.exc_info())
    print('Debug log:')
    patch.setdebug()
    patchset.apply(root=venv)
else:
    print('successfully patched')
