import aiofiles
import os
import sys
import tarfile
import zipfile
from pathlib import Path
from async_files.utils import async_wraps
from async_files import FileIO
from async_files.fileobj import DEFAULT_CONFIG, FileObj
from sanic.log import logger
from . import async_rmtree, async_exists, async_walk

TARBALL_CONFIG = DEFAULT_CONFIG
TARBALL_CONFIG["strings_async_attrs"].extend(["add", "extract", "extractall"])


class TarballFileObj(FileObj):
    CONFIG = TARBALL_CONFIG
    add: callable
    extract: callable
    extractall: callable

class async_open(FileIO):
    OPEN = tarfile.open
    FILEOBJ = TarballFileObj

async def make_tarfile_from_dir(output_filename, source_dir):
    if not output_filename.endswith('.gz'):
        output_filename += '.tar.gz'
    async with async_open(output_filename, "w:gz") as tar:
        await tar.add(source_dir, arcname='.')

    return output_filename

async def make_tarfile(output_filename, files):
    if not output_filename.endswith('.gz'):
        output_filename += '.tar.gz'
    async with async_open(output_filename, "w:gz") as tar:
        for f in files:
            await tar.add(f)

    return output_filename

async def empty_folder(folder):
    for root, dirs, files in await async_walk(folder):
        for f in files:
            await aiofiles.os.remove(os.path.join(root, f))
        for d in dirs:
            await async_rmtree(os.path.join(root, d))

async def pack_files(filename, src, dst):
    output = os.path.join(dst, filename)

    if not await async_exists(src):
        logger.error('Source files {} do not exist'.format(src))
        return None

    try:
        output = await make_tarfile_from_dir(output, src)
    except Exception as e:
        logger.exception(e)
        return None
    else:
        return output

#@async_wraps    # let caller make it async as it's a recursive function
def path_to_dict(path):
    d = {'label': os.path.basename(path)}
    if os.path.isdir(path):
        d['type'] = "directory"
        d['children'] = sorted([path_to_dict(os.path.join(path,x)) for x in os.listdir(path)], key=lambda x: x['type'] == 'directory')
    else:
        d['type'] = "file"
    return d
