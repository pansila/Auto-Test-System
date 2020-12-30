#!/usr/bin/env python3

"""
Bundle the converter.

Inspiration: https://github.com/python-poetry/poetry/pull/2682
"""

from argparse import ArgumentParser
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import os.path
import sys

from clikit.api.io.flags import DEBUG  # type: ignore
from clikit.io import ConsoleIO, NullIO  # type: ignore
from poetry.core.masonry.builders.wheel import WheelBuilder  # type: ignore
from poetry.core.packages import Package  # type: ignore
from poetry.core.semver.version import Version  # type: ignore
from poetry.factory import Factory  # type: ignore
from poetry.installation.installer import Installer  # type: ignore
from poetry.installation.operations.install import Install  # type: ignore
from poetry.utils.env import EnvManager, SystemEnv, VirtualEnv  # type: ignore
from poetry.utils.helpers import temporary_directory  # type: ignore


def bundle(
    zip_file, source_dir, *more_root_files, build_dir=None, clean=False, verbose=False
):
    "Bundle the package into a ZIP file."

    io = ConsoleIO()
    if args.verbose:
        io.set_verbosity(DEBUG)

    with _build_directory(build_dir) as build_dir:
        build_dir = Path(build_dir)
        poetry = Factory().create_poetry(cwd=source_dir, io=io)
        env = _sane_env(poetry, build_dir, io, clean=clean)
        _install_deps(poetry, env, io)
        _install_package(poetry, env, io)
        _zip(zip_file, build_dir, *[source_dir / f for f in more_root_files])


@contextmanager
def _named_build_directory(build_dir):
    "Context manager for a named build directory."
    yield Path(build_dir)


def _build_directory(build_dir):
    "Return a context manager for our build directory."
    if build_dir:
        return _named_build_directory(build_dir)
    return temporary_directory()


def _sane_env(poetry, build_dir, io, clean=False):
    "Yield a sane virtual environment in build_dir."
    manager = EnvManager(poetry)
    if os.path.isdir(build_dir):
        env = VirtualEnv(build_dir)
        if clean or (not env.is_sane()):
            io.write_line(f"removing env {build_dir}")
            manager.remove_venv(build_dir)
    if not os.path.isdir(build_dir):
        io.write_line(f"building env {build_dir}")
        manager.build_venv(build_dir, executable=None)
    return VirtualEnv(build_dir)


def _install_deps(poetry, env, io):
    "Install dependencies."
    installer = _make_installer(poetry, env, io)
    assert installer.run() == 0


def _install_package(poetry, env, io):
    "Install package."
    with temporary_directory() as directory:
        wheel_name = WheelBuilder.make_in(poetry, directory=Path(directory))
        wheel = Path(directory).joinpath(wheel_name)
        package = Package(
            poetry.package.name,
            poetry.package.version,
            source_type="file",
            source_url=wheel,
        )
        _make_installer(poetry, env, io).executor.execute([Install(package)])


def _make_installer(poetry, env, io):
    "Make a fresh installer."
    installer = Installer(
        NullIO() if not io.is_debug() else io,
        env,
        poetry.package,
        poetry.locker,
        poetry.pool,
        poetry.config,
    )
    installer.dev_mode(False)
    installer.remove_untracked()
    installer.use_executor(poetry.config.get("experimental.new-installer", False))
    return installer


def _zip(zip_file, build_dir, *more_root_files):
    "Zip the files up."
    version_info = SystemEnv(Path(sys.prefix)).get_version_info()
    python_minor = Version(*version_info[:2])
    with ZipFile(zip_file, mode="w", compression=ZIP_DEFLATED, allowZip64=False) as zf:
        for root_file in more_root_files:
            zf.write(root_file, root_file.name)

        for lib in ["lib", "lib64"]:
            target_path = build_dir / lib / f"python{python_minor}" / "site-packages"
            if not target_path.is_dir():
                continue
            for root, dirs, files in os.walk(target_path):
                root_path = Path(root)
                dirs.sort()
                tail_path = root_path.relative_to(target_path)
                if tail_path.parts:
                    zf.write(root_path, tail_path)
                for filename in files:
                    zf.write(root_path / filename, tail_path / filename)


if __name__ == "__main__":
    parser = ArgumentParser(description="bundle our code")
    parser.add_argument("zip_file", metavar="ZIP_FILE", help="path to target ZIP file")
    parser.add_argument(
        "more_root_files",
        metavar="MORE_ROOT_FILES",
        nargs="*",
        help="path to more files to copy into the root of the ZIP file",
    )
    parser.add_argument(
        "-D", "--build-dir", metavar="BUILD_DIR", help="path to build directory"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument(
        "-C",
        "--clean",
        action="store_true",
        help="clean the build directory between uses",
    )
    args = parser.parse_args()
    bundle(
        args.zip_file,
        Path.cwd(),
        *args.more_root_files,
        build_dir=args.build_dir,
        clean=args.clean,
        verbose=args.verbose,
    )
