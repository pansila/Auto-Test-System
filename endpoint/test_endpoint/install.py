import argparse
import os
import subprocess
import sys
import re

def _which_python():
    allowed_executables = ["python3", "python"]
    if sys.platform == 'win32':
        # in favor of 32 bit python to be compatible with the 32bit dlls of test libraries
        allowed_executables[:0] = ["py.exe -3-32", "py.exe -2-32", "py.exe -3-64", "py.exe -2-64"]

    # \d in regex ensures we can convert to int later
    version_matcher = re.compile(r"^Python (?P<major>\d+)\.(?P<minor>\d+)\..+$")
    fallback = None
    for executable in allowed_executables:
        try:
            raw_version = subprocess.check_output(
                executable + " --version", stderr=subprocess.STDOUT, shell=True
            ).decode("utf-8")
        except subprocess.CalledProcessError:
            continue

        match = version_matcher.match(raw_version.strip())
        if match and tuple(map(int, match.groups())) >= (3, 0):
            # favor the first py3 executable we can find.
            return executable

        if fallback is None:
            # keep this one as the fallback; it was the first valid executable we found.
            fallback = executable

    if fallback is None:
        # Avoid breaking existing scripts
        fallback = "python"

    return fallback


def uninstall(root):
    os.chdir(root)
    try:
        subprocess.run('poetry env remove python', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1

def install(root):
    os.chdir(root)
    py_exe = _which_python()
    executable = subprocess.check_output(py_exe + ' -c "import sys; print(sys.executable)"', shell=True, universal_newlines=True)
    try:
        ret = subprocess.run('poetry env use ' + executable, shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1
    try:
        subprocess.run('poetry install', shell=True, check=True, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(e.output)
        return -1

def run_install():
    root = os.path.dirname(os.path.realpath(__file__))
    install(root)

    install(os.path.join(os.path.dirname(root), 'workspace'))

def run_uninstall():
    root = os.path.dirname(os.path.realpath(__file__))
    uninstall(root)

    uninstall(os.path.join(os.path.dirname(root), 'workspace'))

if __name__ == '__main__':
    sys.exit(run_install())
