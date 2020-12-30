from tempfile import TemporaryDirectory as _TemporaryDirectory
from async_files.utils import async_wraps
from async_files.fileio import FileIOMeta

class TemporaryDirectory(metaclass=FileIOMeta):
    OPEN = _TemporaryDirectory

    def __init__(self, *args, **kwargs):
        self.bound_args = self.__signature__.bind(*args, **kwargs)
        self.bound_args.apply_defaults()

    async def __call__(self):
        return await self.open()

    async def open(self):
        self._directory = await self.__class__.OPEN(**self.bound_args.arguments)
        return self._directory.name

    async def __aenter__(self):
        return await self.open()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await async_wraps(self._directory.cleanup)()
