import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import configparser
from contextlib import contextmanager

from .venv_run import empty_folder


def bundle_cleanup(root):
    dist = os.path.join(root, 'dist')
    if os.path.exists(dist):
        shutil.rmtree(dist)

    workspace = os.path.join(root, 'workspace')
    ws_downloads = os.path.join(workspace, 'downloads')
    empty_folder(ws_downloads)
    ws_resources = os.path.join(workspace, 'resources')
    empty_folder(ws_resources)

    pycache = os.path.join(os.path.dirname(__file__), '__pycache__')
    if os.path.exists(pycache):
        shutil.rmtree(pycache)

@contextmanager
def cleanup_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path)
    join_id = config['tool.collie.settings']['join_id']
    uuid = config['tool.collie.settings']['uuid']
    config['tool.collie.settings']['join_id'] = '""'
    config['tool.collie.settings']['uuid'] = '""'
    with open(config_path, 'w') as config_file:
        config.write(config_file)
    yield
    config['tool.collie.settings']['join_id'] = f'{join_id}'
    config['tool.collie.settings']['uuid'] = f'{uuid}'
    with open(config_path, 'w') as config_file:
        config.write(config_file)

def run():
    from .__version__ import __version__
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', help='specify the distribution direcotry')
    args = parser.parse_args()

    root = os.path.join(os.path.realpath(__file__), '..', '..', '..', 'endpoint')
    bundle_cleanup(root)
    with cleanup_config(os.path.join(root, 'pyproject.toml')), tempfile.TemporaryDirectory() as tempDir:
        gzf = os.path.join(tempDir, f'collie-{__version__}.tar.gz')
        with tarfile.open(gzf, "w:gz") as tgz:
            tgz.add(root, arcname='collie')

        sha = hashlib.sha256()
        with open(gzf, 'rb') as f:
            while True:
                buffer = f.read(8192)
                if not buffer:
                    break
                sha.update(buffer)
        checksum = sha.hexdigest()

        cksum_file = os.path.join(tempDir, f'collie-{__version__}.sha256sum')
        with open(cksum_file, 'w') as f:
            f.write(checksum)

        dist = args.dist if args.dist else os.path.join(root, 'dist')
        if not os.path.exists(dist):
            os.mkdir(dist)

        tgz_file = os.path.join(dist, f'collie-{__version__}-linux.tar.gz')
        checksum_file = os.path.join(dist, f'collie-{__version__}-linux.sha256sum')
        shutil.copyfile(cksum_file, checksum_file)
        shutil.copyfile(gzf, tgz_file)

        tgz_file = os.path.join(dist, f'collie-{__version__}-win32.tar.gz')
        checksum_file = os.path.join(dist, f'collie-{__version__}-win32.sha256sum')
        shutil.copyfile(cksum_file, checksum_file)
        shutil.copyfile(gzf, tgz_file)
