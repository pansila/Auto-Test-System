import configparser
import os
import hashlib
import json
import shutil
import sys
import tempfile
import subprocess
import tarfile
import re
import stat
from functools import cmp_to_key
from contextlib import closing
from gzip import GzipFile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen

WINDOWS = sys.platform == "win32"

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

BAT = '@echo off\r\n{python_executable} "{collie_bootstrap}" %*\r\n'
SH = '#!/bin/sh\npython3 "{collie_bootstrap}" $*\n'

def expanduser(path):
    """
    Expand ~ and ~user constructions.

    Includes a workaround for http://bugs.python.org/issue14768
    """
    expanded = os.path.expanduser(path)
    if path.startswith("~/") and expanded.startswith("//"):
        expanded = expanded[1:]
    return expanded

class SelfUpdate:
    VERSION_REGEX = re.compile(
        r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?"
        "("
        "[._-]?"
        r"(?:(stable|beta|b|RC|alpha|a|patch|pl|p)((?:[.-]?\d+)*)?)?"
        "([.-]?dev)?"
        ")?"
        r"(?:\+[^\s]+)?"
    )

    def __init__(self, version=None, force=False):
        config = configparser.ConfigParser()
        config.read(self.config)
        self.server_host = config['tool.collie.settings']['server_host']
        self.server_port = config['tool.collie.settings']['server_port']
        self.join_id = config['tool.collie.settings']['join_id']
        self.uuid = config['tool.collie.settings']['uuid']
        server_host = self.server_host.strip('"')
        server_port = self.server_port.strip('"')
        self.SERVER_URL = f'http://{server_host}:{server_port}/api_v1'
        self.METADATA_URL = self.SERVER_URL + "/setting/get-endpoint/json"
        self.BASE_URL = self.SERVER_URL + "/setting/download"
        self._version = None if isinstance(version, bool) else version
        self._force = force

    @property
    def home(self):
        if os.environ.get("COLLIE_HOME"):
            return Path(expanduser(os.environ["COLLIE_HOME"]))

        home = Path(expanduser("~"))

        return home / ".collie"

    @property
    def bin(self):
        return self.home / "bin"

    @property
    def lib(self):
        return self.home / "lib"

    @property
    def lib_backup(self):
        return self.home / "lib-backup"

    @property
    def config(self):
        return self.home / "lib" / 'collie' / 'pyproject.toml'

    def get_version(self):
        from .__version__ import __version__
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

        releases = sorted(
            metadata["releases"], key=cmp_to_key(_compare_versions)
        )

        if self._version and self._version not in releases:
            print("Version {} does not exist.".format(self._version))

            return None, None

        version = self._version
        if not version:
            for release in reversed(releases):
                m = self.VERSION_REGEX.match(release)
                if m.group(5) and not self.allows_prereleases():
                    continue

                version = release

                break

        current_version = __version__

        if current_version == version and not self._force:
            print("Latest version already installed.")
            return None, current_version

        return version, current_version

    def run(self):
        version, current_version = self.get_version()
        if not version:
            return

        self.update(version)

        self.restore_config()
        print(f'Succeeded to update collie to version {version}')

    def update(self, version):
        if self.lib_backup.exists():
            shutil.rmtree(str(self.lib_backup))

        # Backup the current installation
        if self.lib.exists():
            shutil.copytree(str(self.lib), str(self.lib_backup))
            shutil.rmtree(str(self.lib))

        try:
            self._update(version)
        except Exception:
            if not self.lib_backup.exists():
                raise

            shutil.copytree(str(self.lib_backup), str(self.lib))
            shutil.rmtree(str(self.lib_backup))

            raise
        finally:
            if self.lib_backup.exists():
                shutil.rmtree(str(self.lib_backup))

        self.make_bin()

    def _update(self, version):
        release_name = self._get_release_name(version)

        base_url = self.BASE_URL + '?'
        name = f"{release_name}.tar.gz"
        checksum = f"{release_name}.sha256sum"

        try:
            r = urlopen(base_url + "file={}".format(checksum))
        except HTTPError as e:
            if e.code == 404:
                raise RuntimeError("Could not find {} file".format(checksum))

            raise

        checksum = r.read().decode().strip()

        try:
            r = urlopen(base_url + "file={}".format(name))
        except HTTPError as e:
            if e.code == 404:
                raise RuntimeError("Could not find {} file".format(name))

            raise

        meta = r.info()
        size = int(meta["Content-Length"])
        current = 0
        block_size = 8192

        sha = hashlib.sha256()
        with tempfile.TemporaryDirectory(prefix="collie-updater-") as dir_:
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
                    f.extractall(str(self.lib))
            finally:
                gz.close()

    def restore_config(self):
        config = configparser.ConfigParser()
        config.read(self.config)
        config['tool.collie.settings']['server_host'] = self.server_host
        config['tool.collie.settings']['server_port'] = self.server_port
        config['tool.collie.settings']['join_id'] = self.join_id
        config['tool.collie.settings']['uuid'] = self.uuid
        with open(self.config, 'w') as config_file:
            config.write(config_file)

    def process(self, *args):
        return subprocess.check_output(list(args), stderr=subprocess.STDOUT)

    def _check_recommended_installation(self):
        current = Path(__file__)
        try:
            current.relative_to(self.home)
        except ValueError:
            raise RuntimeError(
                "Collie was not installed with the recommended installer. "
                "Cannot update automatically."
            )

    def _get_release_name(self, version):
        platform = sys.platform
        if platform == "linux2":
            platform = "linux"

        return "collie-{}-{}".format(version, platform)

    def _bin_path(self, base_path, bin):
        if WINDOWS:
            return (base_path / "Scripts" / bin).with_suffix(".exe")

        return base_path / "bin" / bin

    def make_bin(self):
        self.bin.mkdir(0o755, parents=True, exist_ok=True)

        python_executable = self._which_python()

        with self.bin.joinpath("bootstrap.py").open("w", newline="") as f:
            f.write(BOOTSTRAP.format(collie_bin=str(self.bin / "collie.py")))

        if WINDOWS:
            with self.bin.joinpath("collie.bat").open("w", newline="") as f:
                f.write(
                    BAT.format(
                        python_executable=python_executable,
                        collie_bootstrap=str(self.bin / "bootstrap.py").replace(
                            os.environ["USERPROFILE"], "%USERPROFILE%"
                        ),
                    )
                )
        else:
            with self.bin.joinpath("collie").open("w", newline="") as f:
                f.write(
                    SH.format(
                        collie_bootstrap=str(self.bin / "bootstrap.py").replace(
                            os.getenv("HOME", ""), "$HOME"
                        ),
                    )
                )

        bin_content = BIN
        if not WINDOWS:
            bin_content = "#!/usr/bin/env {}\n".format(python_executable) + bin_content

        self.bin.joinpath("collie.py").write_text(bin_content, encoding="utf-8")

        if not WINDOWS:
            # Making the file executable
            st = os.stat(str(self.bin.joinpath("collie")))
            os.chmod(str(self.bin.joinpath("collie")), st.st_mode | stat.S_IEXEC)

    def _which_python(self):
        """
        Decides which python executable we'll embed in the launcher script.
        """
        allowed_executables = ["python", "python3"]
        if WINDOWS:
            allowed_executables += ["py.exe -3", "py.exe -2"]

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

    def _get(self, url):
        request = Request(url, headers={"User-Agent": "Python Robotest"})

        with closing(urlopen(request)) as r:
            return r.read()

    def update_join_id(self, join_id):
        config = configparser.ConfigParser()
        config.read(self.config)
        config['tool.collie.settings']['join_id'] = f'"{join_id}"'
        with open(self.config, 'w') as config_file:
            config.write(config_file)
