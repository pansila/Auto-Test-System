import hashlib
import os
import shutil
import sys
import tarfile
import tempfile

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

def run():
    from .__version__ import __version__
    root = os.path.join(os.path.realpath(__file__), '..', '..', '..', 'endpoint')
    bundle_cleanup(root)

    with tempfile.TemporaryDirectory() as tempDir:
        gzf = os.path.join(tempDir, f'robotest-{__version__}.tar.gz')
        with tarfile.open(gzf, "w:gz") as tgz:
            tgz.add(root, arcname='robotest')

        sha = hashlib.sha256()
        with open(gzf, 'rb') as f:
            while True:
                buffer = f.read(8192)
                if not buffer:
                    break
                sha.update(buffer)
        checksum = sha.hexdigest()

        cksum_file = os.path.join(tempDir, f'robotest-{__version__}.sha256sum')
        with open(cksum_file, 'w') as f:
            f.write(checksum)

        dist = os.path.join(root, 'dist')
        if not os.path.exists(dist):
            os.mkdir(dist)

        tgz_file = os.path.join(dist, f'robotest-{__version__}-linux.tar.gz')
        checksum_file = os.path.join(dist, f'robotest-{__version__}-linux.sha256sum')
        shutil.copyfile(cksum_file, checksum_file)
        shutil.copyfile(gzf, tgz_file)

        tgz_file = os.path.join(dist, f'robotest-{__version__}-win32.tar.gz')
        checksum_file = os.path.join(dist, f'robotest-{__version__}-win32.sha256sum')
        shutil.copyfile(cksum_file, checksum_file)
        shutil.copyfile(gzf, tgz_file)
