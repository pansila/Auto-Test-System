import os
import site
import subprocess
import sys
from contextlib import contextmanager
from copy import copy


def empty_folder(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

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
    else:
        os.environ['PATH'] = os.path.dirname(os.path.join(venv, 'bin')) + os.pathsep + old_os_path
        site_packages = os.path.join(venv, 'lib', 'python%s' % sys.version[:3], 'site-packages')
    prev_sys_path = list(sys.path)
    site.addsitedir(site_packages)
    sys.real_prefix = sys.prefix
    sys.prefix = venv
    # Move the added items to the front of the path:
    new_sys_path = []
    for item in list(sys.path):
        if item not in prev_sys_path:
            new_sys_path.append(item)
            sys.path.remove(item)
    sys.path[:0] = new_sys_path
    yield
    os.environ['PATH'] = old_os_path
    sys.path = prev_sys_path

@contextmanager
def activate_workspace(workspace):
    if not os.path.exists(os.path.join(workspace, 'pyproject.toml')):
        raise RuntimeError('workspace\'s configuration file pyproject.toml not found')
    with pushd(workspace):
        try:
            env = copy(dict(os.environ))
            if 'VIRTUAL_ENV' in os.environ:
                del env['VIRTUAL_ENV']
            subprocess.check_output('poetry env info --path', shell=True, universal_newlines=True, env=env)
        except subprocess.CalledProcessError as e:
            raise AssertionError(f'Failed to get the virtual environment path, please ensure that poetry is in the PATH and virtualenv for workspace has been created')
        with activate_venv(venv):
            yield

def start():
    with activate_workspace(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))):
        from .main import run
        run()
