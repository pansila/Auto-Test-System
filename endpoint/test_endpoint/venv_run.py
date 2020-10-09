import os
import site
import subprocess
import sys
import shutil
from contextlib import contextmanager
from copy import copy


def empty_folder(folder):
    if not os.path.exists(folder):
        os.mkdir(folder)
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

def remove_duplicate(in_list):
    known_list = set()
    new_list = []
    for e in in_list:
        if e in known_list: continue
        known_list.add(e)
        new_list.append(e)
    return new_list

@contextmanager
def pushd(new_path):
    old_path = os.getcwd()
    os.chdir(new_path)
    yield
    os.chdir(old_path)

@contextmanager
def activate_venv(venv):
    old_os_path = os.environ.get('PATH', '')
    if sys.platform == 'win32':
        os.environ['PATH'] = os.path.dirname(os.path.join(venv, 'Scripts')) + os.pathsep + old_os_path
        site_packages = os.path.join(venv, 'Lib', 'site-packages')
        executable = os.path.join(venv, 'Scripts', 'python.exe')
    else:
        os.environ['PATH'] = os.path.dirname(os.path.join(venv, 'bin')) + os.pathsep + old_os_path
        site_packages = os.path.join(venv, 'lib', 'python%s' % sys.version[:3], 'site-packages')
        executable = os.path.join(venv, 'bin', 'python')
    sys_path = eval(subprocess.check_output([executable, '-c', 'import sys; print(sys.path)'], universal_newlines=True))
    if not isinstance(sys_path, list):
	    raise AssertionError('Can\'t find the sys.path of the virtual environment')
    old_virtual_env = os.environ.get("VIRTUAL_ENV", '')
    os.environ["VIRTUAL_ENV"] = venv
    prev = set(sys.path)
    site.addsitedir(site_packages)
    sys.real_prefix = sys.prefix
    sys.prefix = venv
    # Move the added items to the front of the path:
    new = list(sys.path)
    sys.path[:] = remove_duplicate([i for i in new if i not in prev] + sys_path + [i for i in new if i in prev])
    yield
    os.environ['PATH'] = old_os_path
    os.environ["VIRTUAL_ENV"] = old_virtual_env
    sys.path = list(prev)

def get_venv():
    try:
        env = copy(dict(os.environ))
        if 'VIRTUAL_ENV' in os.environ:
            del env['VIRTUAL_ENV']
        venv = subprocess.check_output('poetry env info --path', shell=True, universal_newlines=True, env=env).strip()
    except subprocess.CalledProcessError as e:
        raise AssertionError(f'Failed to get the virtual environment path, please ensure that poetry is in the PATH and virtualenv for workspace has been created')
    else:
        return venv

@contextmanager
def activate_workspace(workspace):
    if not os.path.exists(os.path.join(workspace, 'pyproject.toml')):
        raise RuntimeError('workspace\'s configuration file pyproject.toml not found')
    with pushd(workspace):
        venv = get_venv()
        with activate_venv(venv):
            yield venv

def start(host=None, port=None, debug=False):
    with activate_workspace(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))):
        from .main import run
        run(host, port, debug)
