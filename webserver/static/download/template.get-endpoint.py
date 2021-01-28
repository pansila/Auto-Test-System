import argparse
import configparser
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from contextlib import closing
from contextlib import contextmanager
from functools import cmp_to_key
from gzip import GzipFile
from io import UnsupportedOperation
from io import open
from urllib.parse import urlparse


try:
    from urllib.error import HTTPError
    from urllib.request import Request
    from urllib.request import urlopen
except ImportError:
    from urllib2 import HTTPError
    from urllib2 import Request
    from urllib2 import urlopen

try:
    input = raw_input
except NameError:
    pass


try:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg
except ImportError:
    winreg = None

try:
    u = unicode
except NameError:
    u = str

SHELL = os.getenv("SHELL", "")
WINDOWS = sys.platform.startswith("win") or (sys.platform == "cli" and os.name == "nt")


FOREGROUND_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}

BACKGROUND_COLORS = {
    "black": 40,
    "red": 41,
    "green": 42,
    "yellow": 43,
    "blue": 44,
    "magenta": 45,
    "cyan": 46,
    "white": 47,
}

OPTIONS = {"bold": 1, "underscore": 4, "blink": 5, "reverse": 7, "conceal": 8}


def style(fg, bg, options):
    codes = []

    if fg:
        codes.append(FOREGROUND_COLORS[fg])

    if bg:
        codes.append(BACKGROUND_COLORS[bg])

    if options:
        if not isinstance(options, (list, tuple)):
            options = [options]

        for option in options:
            codes.append(OPTIONS[option])

    return "\033[{}m".format(";".join(map(str, codes)))


STYLES = {
    "info": style("green", None, None),
    "comment": style("yellow", None, None),
    "error": style("red", None, None),
    "warning": style("yellow", None, None),
}


def is_decorated():
    if platform.system().lower() == "windows":
        return (
            os.getenv("ANSICON") is not None
            or "ON" == os.getenv("ConEmuANSI")
            or "xterm" == os.getenv("Term")
        )

    if not hasattr(sys.stdout, "fileno"):
        return False

    try:
        return os.isatty(sys.stdout.fileno())
    except UnsupportedOperation:
        return False


def is_interactive():
    if not hasattr(sys.stdin, "fileno"):
        return False

    try:
        return os.isatty(sys.stdin.fileno())
    except UnsupportedOperation:
        return False


def colorize(style, text):
    if not is_decorated():
        return text

    return "{}{}\033[0m".format(STYLES[style], text)


@contextmanager
def temporary_directory(*args, **kwargs):
    try:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(*args, **kwargs) as name:
            yield name
    except ImportError:
        name = tempfile.mkdtemp(*args, **kwargs)

        yield name

        shutil.rmtree(name)


def string_to_bool(value):
    value = value.lower()

    return value in {"true", "1", "y", "yes"}


def expanduser(path):
    """
    Expand ~ and ~user constructions.

    Includes a workaround for http://bugs.python.org/issue14768
    """
    expanded = os.path.expanduser(path)
    if path.startswith("~/") and expanded.startswith("//"):
        expanded = expanded[1:]

    return expanded


HOME = expanduser("~")
COLLIE_HOME = os.environ.get("COLLIE_HOME") or os.path.join(HOME, ".collie")
COLLIE_BIN = os.path.join(COLLIE_HOME, "bin")
COLLIE_ENV = os.path.join(COLLIE_HOME, "env")
COLLIE_LIB = os.path.join(COLLIE_HOME, "lib")
COLLIE_LIB_BACKUP = os.path.join(COLLIE_HOME, "lib-backup")
COLLIE_CONFIG = os.path.join(COLLIE_LIB, "collie", "pyproject.toml")


BOOTSTRAP = """\
import os, sys
import re
import subprocess

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

if __name__ == '__main__':
    py_executable = _which_python()
    subprocess.run(py_executable + r' {collie_bin} ' + ' '.join(sys.argv[1:]), shell=True)
"""

BIN = """#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import argparse

lib = os.path.normpath(os.path.join(os.path.realpath(__file__), "..", "..", "lib", "collie"))
sys.path.insert(0, lib)

from test_endpoint.app import main

if __name__ == "__main__":
    sys.exit(main())
"""

BAT = u('@echo off\r\npython "{collie_bootstrap}" %*\r\n')
SH = u('#!/bin/sh\npython3 "{collie_bootstrap}" $*\n')


PRE_MESSAGE = """# Welcome to {collie}!

This will download and install the latest version of {collie},
a dependency and package manager for Python.

It will add the `collie` command to {collie}'s bin directory, located at:

{collie_home_bin}

{platform_msg}

You can uninstall at any time by executing this script with the --uninstall option,
and these changes will be reverted.
"""

PRE_UNINSTALL_MESSAGE = """# We are sorry to see you go!

This will uninstall {collie}.

It will remove the `collie` command from {collie}'s bin directory, located at:

{collie_home_bin}

This will also remove {collie} from your system's PATH.
"""


PRE_MESSAGE_UNIX = """This path will then be added to your `PATH` environment variable by
modifying the profile file{plural} located at:

{rcfiles}"""


PRE_MESSAGE_FISH = """This path will then be added to your `PATH` environment variable by
modifying the `fish_user_paths` universal variable."""

PRE_MESSAGE_WINDOWS = """This path will then be added to your `PATH` environment variable by
modifying the `HKEY_CURRENT_USER/Environment/PATH` registry key."""

PRE_MESSAGE_NO_MODIFY_PATH = """This path needs to be in your `PATH` environment variable,
but will not be added automatically."""

POST_MESSAGE_UNIX = """{collie} ({version}) is installed now. Great!

To get started you need {collie}'s bin directory ({collie_home_bin}) in your `PATH`
environment variable. Next time you log in this will be done
automatically.

To configure your current shell run `source {collie_home_env}`

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""

POST_MESSAGE_FISH = """{collie} ({version}) is installed now. Great!

{collie}'s bin directory ({collie_home_bin}) has been added to your `PATH`
environment variable by modifying the `fish_user_paths` universal variable.

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""

POST_MESSAGE_WINDOWS = """{collie} ({version}) is installed now. Great!

To get started you need collie's bin directory ({collie_home_bin}) in your `PATH`
environment variable. Future applications will automatically have the
correct environment, but you may need to restart your current shell.

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""

POST_MESSAGE_UNIX_NO_MODIFY_PATH = """{collie} ({version}) is installed now. Great!

To get started you need {collie}'s bin directory ({collie_home_bin}) in your `PATH`
environment variable.

To configure your current shell run `source {collie_home_env}`

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""

POST_MESSAGE_FISH_NO_MODIFY_PATH = """{collie} ({version}) is installed now. Great!

To get started you need {collie}'s bin directory ({collie_home_bin})
in your `PATH` environment variable, which you can add by running
the following command:

    set -U fish_user_paths {collie_home_bin} $fish_user_paths

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""

POST_MESSAGE_WINDOWS_NO_MODIFY_PATH = """{collie} ({version}) is installed now. Great!

To get started you need collie's bin directory ({collie_home_bin}) in your `PATH`
environment variable. This has not been done automatically.

Before running the test endpoint, you need to prepare the virtual environments of it,
to do so please run `{collie} --install`. Then you can run `{collie}` to start.
"""


class Installer:

    CURRENT_PYTHON = sys.executable
    CURRENT_PYTHON_VERSION = sys.version_info[:2]
    REPOSITORY_URL = "{server_url}"
    METADATA_URL = REPOSITORY_URL + "/setting/get-endpoint/json"
    BASE_URL = REPOSITORY_URL + "/setting/download/"
    VERSION_REGEX = re.compile(
        r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?"
        "("
        "[._-]?"
        r"(?:(stable|beta|b|RC|alpha|a|patch|pl|p)((?:[.-]?\d+)*)?)?"
        "([.-]?dev)?"
        ")?"
        r"(?:\+[^\s]+)?"
    )


    def __init__(
        self,
        version=None,
        preview=False,
        force=False,
        accept_all=False,
        base_url=BASE_URL,
    ):
        self._version = version
        self._preview = preview
        self._force = force
        self._modify_path = True
        self._install_poetry = True
        self._accept_all = accept_all
        self._base_url = base_url
        self._server_ip = None
        self._server_port = None
        self._join_id = None

    def allows_prereleases(self):
        return self._preview

    def run(self):
        version, current_version = self.get_version()

        if version is None:
            return 0

        self.customize_install()
        self.install_poetry()
        self.display_pre_message()
        self.ensure_home()

        try:
            self.install(version, upgrade=current_version is not None)
        except subprocess.CalledProcessError as e:
            print(colorize("error", "An error has occured: {}".format(str(e))))
            print(e.output.decode())

            return e.returncode

        self.display_post_message(version)

        return 0

    def uninstall(self):
        self.display_pre_uninstall_message()

        if not self.customize_uninstall():
            return

        self.remove_home()
        self.remove_from_path()

    def install_poetry(self):
        if not self._install_poetry:
            return

        url = self._base_url.rstrip('/') + '?'
        get_poetry = "get-poetry.py"

        try:
            r = urlopen(url + "file={}".format(get_poetry))
        except HTTPError as e:
            if e.code == 404:
                raise RuntimeError("Could not find {} file".format(get_poetry))

            raise

        with temporary_directory(prefix="poetry-installer-") as dir_:
            temp = os.path.realpath(os.path.join(dir_, get_poetry))
            with open(temp, 'wb') as f:
                f.write(r.read())
            force = '--force' if self._force else ''
            preview = '--preview' if self._preview else ''
            subprocess.run(f'python {temp} {force} {preview}', shell=True, check=True)

    def get_version(self):
        print(colorize("info", "Retrieving collie metadata"))

        metadata = json.loads(self._get(self.METADATA_URL).decode())

        def _compare_versions(x, y):
            mx = self.VERSION_REGEX.match(x)
            my = self.VERSION_REGEX.match(y)

            vx = tuple(int(p) for p in mx.groups()[:3]) + (mx.group(5),)
            vy = tuple(int(p) for p in my.groups()[:3]) + (my.group(5),)

            if vx < vy:
                return -1
            elif vx > vy:
                return 1

            return 0

        print("")
        releases = sorted(
            metadata["releases"], key=cmp_to_key(_compare_versions)
        )

        if self._version and self._version not in releases:
            print(colorize("error", "Version {} does not exist.".format(self._version)))

            return None, None

        version = self._version
        if not version:
            for release in reversed(releases):
                m = self.VERSION_REGEX.match(release)
                if m.group(5) and not self.allows_prereleases():
                    continue

                version = release

                break

        current_version = None
        if os.path.exists(COLLIE_LIB):
            with open(
                os.path.join(COLLIE_LIB, "collie", "test_endpoint", "__version__.py"), encoding="utf-8"
            ) as f:
                version_content = f.read()

            current_version_re = re.match(
                '(?ms).*__version__ = "(.+)".*', version_content
            )
            if not current_version_re:
                print(
                    colorize(
                        "warning",
                        "Unable to get the current collie version. Assuming None",
                    )
                )
            else:
                current_version = current_version_re.group(1)

        if current_version == version and not self._force:
            print("Latest version already installed.")
            return None, current_version

        return version, current_version

    def customize_install(self):
        if not self._accept_all:
            print("Before we start, please answer the following questions.")
            print("You may simply press the Enter key to leave unchanged.")

            modify_path = input("Modify PATH variable? ([y]/n) ") or "y"
            if modify_path.lower() in {"n", "no"}:
                self._modify_path = False

            install_poetry = input("Install poetry? ([y]/n) ") or "y"
            if install_poetry.lower() in {"n", "no"}:
                self._install_poetry = False

            self._server_ip = input("Please specify the server IP address ({server_url}):") or "{server_url}"
            self._server_ip = urlparse(self._server_ip).netloc
            self._join_id = input("Please specify the organization or team's ID to join:") or ''

            print("")

    def customize_uninstall(self):
        if not self._accept_all:
            print()

            uninstall = (
                input("Are you sure you want to uninstall collie? (y/[n]) ") or "n"
            )
            if uninstall.lower() not in {"y", "yes"}:
                return False

            print("")

        return True

    def ensure_home(self):
        """
        Ensures that $COLLIE_HOME exists or create it.
        """
        if not os.path.exists(COLLIE_HOME):
            os.mkdir(COLLIE_HOME, 0o755)

    def remove_home(self):
        """
        Removes $COLLIE_HOME.
        """
        if not os.path.exists(COLLIE_HOME):
            return

        shutil.rmtree(COLLIE_HOME)

    def install(self, version, upgrade=False):
        """
        Installs collie in $COLLIE_HOME.
        """
        print("Installing version: " + colorize("info", version))

        self.make_lib(version)
        self.update_config()
        self.make_bin()
        self.make_env()
        self.update_path()

        return 0

    def make_lib(self, version):
        """
        Packs everything into a single lib/ directory.
        """
        if os.path.exists(COLLIE_LIB_BACKUP):
            shutil.rmtree(COLLIE_LIB_BACKUP)

        # Backup the current installation
        if os.path.exists(COLLIE_LIB):
            shutil.copytree(COLLIE_LIB, COLLIE_LIB_BACKUP)
            shutil.rmtree(COLLIE_LIB)

        try:
            self._make_lib(version)
        except Exception:
            if not os.path.exists(COLLIE_LIB_BACKUP):
                raise

            shutil.copytree(COLLIE_LIB_BACKUP, COLLIE_LIB)
            shutil.rmtree(COLLIE_LIB_BACKUP)

            raise
        finally:
            if os.path.exists(COLLIE_LIB_BACKUP):
                shutil.rmtree(COLLIE_LIB_BACKUP)

    def _make_lib(self, version):
        # We get the payload from the remote host
        platform = sys.platform
        if platform == "linux2":
            platform = "linux"

        url = self._base_url.rstrip('/') + '?'
        name = "collie-{}-{}.tar.gz".format(version, platform)
        checksum = "collie-{}-{}.sha256sum".format(version, platform)

        try:
            r = urlopen(url + "file={}".format(checksum))
        except HTTPError as e:
            if e.code == 404:
                raise RuntimeError("Could not find {} file".format(checksum))

            raise

        checksum = r.read().decode()

        try:
            r = urlopen(url + "file={}".format(name))
        except HTTPError as e:
            if e.code == 404:
                raise RuntimeError("Could not find {} file".format(name))

            raise

        meta = r.info()
        size = int(meta["Content-Length"])
        current = 0
        block_size = 8192

        print(
            "  - Downloading {} ({:.2f}MB)".format(
                colorize("comment", name), size / 1024 / 1024
            )
        )

        sha = hashlib.sha256()
        with temporary_directory(prefix="collie-installer-") as dir_:
            tar = os.path.join(dir_, name)
            with open(tar, "wb") as f:
                while True:
                    buffer = r.read(block_size)
                    if not buffer:
                        break

                    current += len(buffer)
                    f.write(buffer)
                    sha.update(buffer)

            # Checking hashes
            if checksum != sha.hexdigest():
                raise RuntimeError(
                    "Hashes for {} do not match: {} != {}".format(
                        name, checksum, sha.hexdigest()
                    )
                )

            gz = GzipFile(tar, mode="rb")
            try:
                with tarfile.TarFile(tar, fileobj=gz, format=tarfile.PAX_FORMAT) as f:
                    f.extractall(COLLIE_LIB)
            finally:
                gz.close()

    def update_config(self):
        config = configparser.ConfigParser()
        config.read(COLLIE_CONFIG)
        ip, port = self._server_ip.split(':')
        config['tool.collie.settings']['server_host'] = f'"{ip}"'
        config['tool.collie.settings']['server_port'] = f'"{port}"'
        config['tool.collie.settings']['join_id'] = f'"{self._join_id}"'
        config['tool.collie.settings']['uuid'] = '""'
        with open(COLLIE_CONFIG, 'w') as config_file:
            config.write(config_file)

    def make_bin(self):
        if not os.path.exists(COLLIE_BIN):
            os.mkdir(COLLIE_BIN, 0o755)

        with open(os.path.join(COLLIE_BIN, "bootstrap.py"), "w") as f:
            f.write(
                u(
                    BOOTSTRAP.format(
                        collie_bin=os.path.join(COLLIE_BIN, "collie.py").replace(
                            os.environ["USERPROFILE"], "%USERPROFILE%"
                        )
                    )
                )
            )

        if WINDOWS:
            with open(os.path.join(COLLIE_BIN, "collie.bat"), "w") as f:
                f.write(
                    u(
                        BAT.format(
                            collie_bootstrap=os.path.join(COLLIE_BIN, "bootstrap.py").replace(
                                os.environ["USERPROFILE"], "%USERPROFILE%"
                            )
                        )
                    )
                )
        else:
            with open(os.path.join(COLLIE_BIN, "collie"), "w") as f:
                f.write(
                    u(
                        SH.format(
                            collie_bootstrap=os.path.join(COLLIE_BIN, "bootstrap.py").replace(
                                os.getenv("HOME", ""), "$HOME"
                            )
                        )
                    )
                )

        with open(os.path.join(COLLIE_BIN, "collie.py"), "w", encoding="utf-8") as f:
            f.write(u(BIN))

        if not WINDOWS:
            # Making the file executable
            st = os.stat(os.path.join(COLLIE_BIN, "collie"))
            os.chmod(os.path.join(COLLIE_BIN, "collie"), st.st_mode | stat.S_IEXEC)

    def make_env(self):
        if WINDOWS:
            return

        with open(os.path.join(COLLIE_HOME, "env"), "w") as f:
            f.write(u(self.get_export_string()))

    def update_path(self):
        """
        Tries to update the $PATH automatically.
        """
        if not self._modify_path:
            return

        if "fish" in SHELL:
            return self.add_to_fish_path()

        if WINDOWS:
            return self.add_to_windows_path()

        # Updating any profile we can on UNIX systems
        export_string = self.get_export_string()

        addition = "\n{}\n".format(export_string)

        profiles = self.get_unix_profiles()
        for profile in profiles:
            if not os.path.exists(profile):
                continue

            with open(profile, "r") as f:
                content = f.read()

            if addition not in content:
                with open(profile, "a") as f:
                    f.write(u(addition))

    def add_to_fish_path(self):
        """
        Ensure COLLIE_BIN directory is on Fish shell $PATH
        """
        current_path = os.environ.get("PATH", None)
        if current_path is None:
            print(
                colorize(
                    "warning",
                    "\nUnable to get the PATH value. It will not be updated automatically.",
                )
            )
            self._modify_path = False

            return

        if COLLIE_BIN not in current_path:
            fish_user_paths = subprocess.check_output(
                ["fish", "-c", "echo $fish_user_paths"]
            ).decode("utf-8")
            if COLLIE_BIN not in fish_user_paths:
                cmd = "set -U fish_user_paths {} $fish_user_paths".format(COLLIE_BIN)
                set_fish_user_path = ["fish", "-c", "{}".format(cmd)]
                subprocess.check_output(set_fish_user_path)
        else:
            print(
                colorize(
                    "warning",
                    "\nPATH already contains {} and thus was not modified.".format(
                        COLLIE_BIN
                    ),
                )
            )

    def add_to_windows_path(self):
        try:
            old_path = self.get_windows_path_var()
        except WindowsError:
            old_path = None

        if old_path is None:
            print(
                colorize(
                    "warning",
                    "Unable to get the PATH value. It will not be updated automatically",
                )
            )
            self._modify_path = False

            return

        new_path = COLLIE_BIN
        if COLLIE_BIN in old_path:
            old_path = old_path.replace(COLLIE_BIN + ";", "")

        if old_path:
            new_path += ";"
            new_path += old_path

        self.set_windows_path_var(new_path)

    def get_windows_path_var(self):
        with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as root:
            with winreg.OpenKey(root, "Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                path, _ = winreg.QueryValueEx(key, "PATH")

                return path

    def set_windows_path_var(self, value):
        import ctypes

        with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as root:
            with winreg.OpenKey(root, "Environment", 0, winreg.KEY_ALL_ACCESS) as key:
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, value)

        # Tell other processes to update their environment
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x1A

        SMTO_ABORTIFHUNG = 0x0002

        result = ctypes.c_long()
        SendMessageTimeoutW = ctypes.windll.user32.SendMessageTimeoutW
        SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            u"Environment",
            SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(result),
        )

    def remove_from_path(self):
        if "fish" in SHELL:
            return self.remove_from_fish_path()

        elif WINDOWS:
            return self.remove_from_windows_path()

        return self.remove_from_unix_path()

    def remove_from_fish_path(self):
        fish_user_paths = subprocess.check_output(
            ["fish", "-c", "echo $fish_user_paths"]
        ).decode("utf-8")
        if COLLIE_BIN in fish_user_paths:
            cmd = "set -U fish_user_paths (string match -v {} $fish_user_paths)".format(
                COLLIE_BIN
            )
            set_fish_user_path = ["fish", "-c", "{}".format(cmd)]
            subprocess.check_output(set_fish_user_path)

    def remove_from_windows_path(self):
        path = self.get_windows_path_var()

        collie_path = COLLIE_BIN
        if collie_path in path:
            path = path.replace(COLLIE_BIN + ";", "")

            if collie_path in path:
                path = path.replace(COLLIE_BIN, "")

        self.set_windows_path_var(path)

    def remove_from_unix_path(self):
        # Updating any profile we can on UNIX systems
        export_string = self.get_export_string()

        addition = "{}\n".format(export_string)

        profiles = self.get_unix_profiles()
        for profile in profiles:
            if not os.path.exists(profile):
                continue

            with open(profile, "r") as f:
                content = f.readlines()

            if addition not in content:
                continue

            new_content = []
            for line in content:
                if line == addition:
                    if new_content and not new_content[-1].strip():
                        new_content = new_content[:-1]

                    continue

                new_content.append(line)

            with open(profile, "w") as f:
                f.writelines(new_content)

    def get_export_string(self):
        path = COLLIE_BIN.replace(os.getenv("HOME", ""), "$HOME")
        export_string = 'export PATH="{}:$PATH"'.format(path)

        return export_string

    def get_unix_profiles(self):
        profiles = [os.path.join(HOME, ".profile")]

        if "zsh" in SHELL:
            zdotdir = os.getenv("ZDOTDIR", HOME)
            profiles.append(os.path.join(zdotdir, ".zprofile"))

        bash_profile = os.path.join(HOME, ".bash_profile")
        if os.path.exists(bash_profile):
            profiles.append(bash_profile)

        return profiles

    def display_pre_message(self):
        if WINDOWS:
            home = COLLIE_BIN.replace(os.getenv("USERPROFILE", ""), "%USERPROFILE%")
        else:
            home = COLLIE_BIN.replace(os.getenv("HOME", ""), "$HOME")

        kwargs = {
            "collie": colorize("info", "collie"),
            "collie_home_bin": colorize("comment", home),
        }

        if not self._modify_path:
            kwargs["platform_msg"] = PRE_MESSAGE_NO_MODIFY_PATH
        else:
            if "fish" in SHELL:
                kwargs["platform_msg"] = PRE_MESSAGE_FISH
            elif WINDOWS:
                kwargs["platform_msg"] = PRE_MESSAGE_WINDOWS
            else:
                profiles = [
                    colorize("comment", p.replace(os.getenv("HOME", ""), "$HOME"))
                    for p in self.get_unix_profiles()
                ]
                kwargs["platform_msg"] = PRE_MESSAGE_UNIX.format(
                    rcfiles="\n".join(profiles), plural="s" if len(profiles) > 1 else ""
                )

        print(PRE_MESSAGE.format(**kwargs))

    def display_pre_uninstall_message(self):
        home_bin = COLLIE_BIN
        if WINDOWS:
            home_bin = home_bin.replace(os.getenv("USERPROFILE", ""), "%USERPROFILE%")
        else:
            home_bin = home_bin.replace(os.getenv("HOME", ""), "$HOME")

        kwargs = {
            "collie": colorize("info", "collie"),
            "collie_home_bin": colorize("comment", home_bin),
        }

        print(PRE_UNINSTALL_MESSAGE.format(**kwargs))

    def display_post_message(self, version):
        print("")

        kwargs = {
            "collie": colorize("info", "collie"),
            "version": colorize("comment", version),
        }

        if WINDOWS:
            message = POST_MESSAGE_WINDOWS
            if not self._modify_path:
                message = POST_MESSAGE_WINDOWS_NO_MODIFY_PATH

            collie_home_bin = COLLIE_BIN.replace(
                os.getenv("USERPROFILE", ""), "%USERPROFILE%"
            )
        elif "fish" in SHELL:
            message = POST_MESSAGE_FISH
            if not self._modify_path:
                message = POST_MESSAGE_FISH_NO_MODIFY_PATH

            collie_home_bin = COLLIE_BIN.replace(os.getenv("HOME", ""), "$HOME")
        else:
            message = POST_MESSAGE_UNIX
            if not self._modify_path:
                message = POST_MESSAGE_UNIX_NO_MODIFY_PATH

            collie_home_bin = COLLIE_BIN.replace(os.getenv("HOME", ""), "$HOME")
            kwargs["collie_home_env"] = colorize(
                "comment", COLLIE_ENV.replace(os.getenv("HOME", ""), "$HOME")
            )

        kwargs["collie_home_bin"] = colorize("comment", collie_home_bin)

        print(message.format(**kwargs))

    def call(self, *args):
        return subprocess.check_output(args, stderr=subprocess.STDOUT)

    def _get(self, url):
        request = Request(url, headers={"User-Agent": "Python Robotest"})

        with closing(urlopen(request)) as r:
            return r.read()


def main():
    parser = argparse.ArgumentParser(
        description="Installs the latest (or given) version of collie"
    )
    parser.add_argument(
        "-p", "--preview", dest="preview", action="store_true", default=False
    )
    parser.add_argument("--version", dest="version")
    parser.add_argument(
        "-f", "--force", dest="force", action="store_true", default=False
    )
    parser.add_argument(
        "-y", "--yes", dest="accept_all", action="store_true", default=False
    )
    parser.add_argument(
        "--uninstall", dest="uninstall", action="store_true", default=False
    )

    args = parser.parse_args()

    base_url = Installer.BASE_URL
    urlopen(Installer.REPOSITORY_URL)

    installer = Installer(
        version=args.version or os.getenv("COLLIE_VERSION"),
        preview=args.preview or string_to_bool(os.getenv("COLLIE_PREVIEW", "0")),
        force=args.force,
        accept_all=args.accept_all
        or string_to_bool(os.getenv("COLLIE_ACCEPT", "0"))
        or not is_interactive(),
        base_url=base_url,
    )

    if args.uninstall or string_to_bool(os.getenv("COLLIE_UNINSTALL", "0")):
        return installer.uninstall()

    return installer.run()


if __name__ == "__main__":
    sys.exit(main())