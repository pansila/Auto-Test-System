import zipfile
from zipfile import ZipFile as _ZipFile
from typing import Awaitable
from typing import Callable

from async_files import FileIO
from async_files.utils import async_wraps
from async_files.fileobj import DEFAULT_CONFIG, FileObj

ZIPFILE_CONFIG = DEFAULT_CONFIG
ZIPFILE_CONFIG["strings_sync_attrs"].append("namelist")


class TarballFileObj(FileObj):
    CONFIG = ZIPFILE_CONFIG
    namelist: callable

class ZipFile(FileIO):
    OPEN = _ZipFile
    FILEOBJ = TarballFileObj

is_zipfile: Callable[[], Awaitable[bytes]] = async_wraps(zipfile.is_zipfile)
