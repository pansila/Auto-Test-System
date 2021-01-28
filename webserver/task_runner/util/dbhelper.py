import argparse
import copy
import datetime
import email
import os
import posixpath
import re
import sys
import shutil
import zipfile
import zipimport
from io import StringIO
from os import path
from pathlib import Path
import pkg_resources
from pkg_resources import Distribution, EggMetadata, parse_version
from wheel import wheelfile
from wheel import pkginfo
from distutils import dir_util

import mistune
from mongoengine import connect
from flask import current_app

sys.path.append('.')
from app.main.model.database import Test, User
from app.main.config import get_config
from app.main.util.get_path import get_back_scripts_root, get_user_scripts_root
from app.main.model.database import Package

METADATA = 'METADATA'
WHEEL_INFO = 'WHEEL'
WHEEL_INFO_RE = re.compile(
    r"""^(?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)
    ((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)
    \.whl|\.dist-info)$""",
    re.VERBOSE).match
VERSION_CHECK = re.compile(r'(?P<name>.*?)(?P<compare>\s*(==|>=|<=|!=)\s*)(?P<version>\d.+?)?$').match
MODULE_IMPORT = re.compile(r'^\s*(import|from)\s+(?P<module>.+?)(#|$|\s+import\s+.+$)').match

def filter_kw(item):
    item = item.strip()
    if item.startswith('${') or item.startswith('@{') or item.startswith('&{'):
        item = item[2:]
        if not item.endswith('}'):
            current_app.logger.error('{ } mismatch for ' + item)
        else:
            item = item[0:-1]
    return item

def get_package_info(package):
    package = str(package)
    name, description, long_description = '', '', ''
    if package.endswith('.whl'):
        wf = wheelfile.WheelFile(package)
        ef = wf.open(posixpath.join(wf.dist_info_path, 'METADATA'))
        pkg_info = pkginfo.read_pkg_info_bytes(ef.read())
        name = pkg_info['Name']
        description = pkg_info['Summary']
        long_description = pkg_info.get_payload()
        ef.close()
        wf.close()
    if package.endswith('.egg'):
        with zipfile.ZipFile(package) as zf:
            with zf.open(posixpath.join('EGG-INFO', 'PKG-INFO')) as fp:
                value = fp.read().decode('utf-8')
                pkg_info = email.parser.Parser().parsestr(value)
                name = pkg_info['Name']
                description = pkg_info['Summary']
                long_description = pkg_info['Description']
                long_description = '\n'.join((line.strip() for line in StringIO(long_description)))
    return name, description, long_description

def meet_version(versions, compare, version):
    """
    versions must be sorted in ascending order
    """
    assert(len(versions) > 0)
    if not compare:
        return version[0]

    ver = parse_version(version)
    if compare == '==':
        if version in versions:
            return version
    elif compare == '>':
        for v in versions:
            if parse_version(v) > ver:
                return v
    elif compare == '<':
        for v in reversed(versions, key=parse_version):
            if parse_version(v) < ver:
                return v
    elif compare == '>=':
        for v in versions:
            if parse_version(v) >= ver:
                return v
    elif compare == '<=':
        for v in reversed(versions, key=parse_version):
            if parse_version(v) <= ver:
                return v
    elif compare == '!=':
        for i, v in enumerate(versions):
            if v == version:
                versions.pop(i)
                break
        return versions[0] if len(versions) > 0 else None
    return None

def query_package(package_name, organization, team, type):
    package = Package.objects(py_packages=package_name, organization=organization, team=team, package_type=type).first()
    if not package:
        package = Package.objects(py_packages=package_name, organization=organization, team=None, package_type=type).first()
        if not package:
            package = Package.objects(py_packages=package_name, organization=None, team=None, package_type=type).first()
            if not package:
                return None
    return package

def get_package_requires(package, organization, team, type):
    if not package.endswith('.egg') or not zipfile.is_zipfile(package):
        current_app.logger.error(f'{package} is not an .egg file')
        return None
    packages = []
    dist = Distribution.from_filename(package, metadata=EggMetadata(zipimport.zipimporter(package)))
    for r in dist.requires():
        name, compare, version = VERSION_CHECK(str(r)).group('name', 'compare', 'version')
        package = Package.objects(py_packages=name, organization=organization, team=team, package_type=type).first()
        ver = meet_version(package.versions, compare, version) if package else None
        if not package or not ver:
            package = Package.objects(py_packages=name, organization=organization, team=None, package_type=type).first()
            ver = meet_version(package.versions, compare, version) if package else None
            if not package or not ver:
                package = Package.objects(py_packages=name, organization=None, team=None, package_type=type).first()
                ver = meet_version(package.versions, compare, version) if package else None
                if not package or not ver:
                    current_app.logger.error(f'package {name} not found or version requirement not meet: {compare}{version}')
                    return None
        packages.append((package, ver))
    return packages

# TODO: rollback if failed in one step
def install_test_suite(package, user, organization, team, pypi_root, proprietary, version=None, installed=None, recursive=False):
    first_package = len(installed) == 0
    pkg_file = package.get_package_by_version(version)
    if not pkg_file:
        current_app.logger.error(f'package file not found for {package.name} with version {version}')
        return False
    pkg_file_path = pypi_root / package.package_name / pkg_file.filename

    if pkg_file_path in installed:
        return True
    installed[pkg_file_path] = True

    requires = get_package_requires(str(pkg_file_path), organization, team, type='Test Suite')
    if requires:
        for pkg, ver in requires:
            ret = install_test_suite(pkg, user, organization, team, pypi_root, proprietary, version=ver, installed=installed)
            if not ret:
                current_app.logger.error(f'Failed to install dependent package {package.name}')
                return False

    if not recursive and not first_package:
        pkg_file.modify(inc__download_times=1)
        return True

    scripts_root = get_user_scripts_root(organization=organization, team=team)
    libraries_root = get_back_scripts_root(organization=organization, team=team)
    with zipfile.ZipFile(pkg_file_path) as zf:
        for f in zf.namelist():
            if f.startswith('EGG-INFO'):
                continue
            dirname = os.path.dirname(f)
            if os.path.exists(scripts_root / dirname):
                shutil.rmtree(scripts_root / dirname)
            if os.path.exists(libraries_root / dirname):
                shutil.rmtree(libraries_root / dirname)

    with zipfile.ZipFile(pkg_file_path) as zf:
        libraries = (f for f in zf.namelist() if not f.startswith('EGG-INFO') and '/scripts/' not in f)
        for l in libraries:
            zf.extract(l, libraries_root)
        scripts = [f for f in zf.namelist() if '/scripts/' in f]
        for s in scripts:
            zf.extract(s, scripts_root)
        new_tests = []
        all_tests = []
        for pkg_name in set((s.split('/', 1)[0] for s in scripts)):
            for f in os.listdir(scripts_root / pkg_name / 'scripts'):
                shutil.move(str(scripts_root / pkg_name / 'scripts' / f), scripts_root / pkg_name)
                test = db_update_test(scripts_root, os.path.join(pkg_name, f), user, organization, team, package, version)
                if test:
                    new_tests.append(test)
            shutil.rmtree(scripts_root / pkg_name / 'scripts')
            tests = Test.objects(path=pkg_name, organization=organization, team=team)
            for test in tests:
                all_tests.append(test)
        tests = set(all_tests) - set(new_tests)
        for test in tests:
            current_app.logger.critical(f'Remove the staled test suite: {test.test_suite}')
            test.delete()
    pkg_file.modify(inc__download_times=1)
    return True

def db_update_test(scripts_dir, script, user, organization, team, package=None, version=None):
    if scripts_dir is None:
        return None
    if not script.endswith('.md'):
        return None

    basename = os.path.basename(script)
    dirname = os.path.dirname(script)
    test_suite = os.path.splitext(basename)[0]
    test = Test.objects(test_suite=test_suite, path=dirname, organization=organization, team=team).first()
    if not test:
        test = Test(path=dirname, author=user, organization=organization, team=team,
                    test_suite=test_suite, package=package, package_version=version)
        test.create_date = datetime.datetime.utcnow()
        test.save()
    else:
        if package and version:
            test.modify(package=package, package_version=version)
        elif test.package:
            test.package.modify(modified=True)
        test.modify(update_date=datetime.datetime.utcnow())

    ret = update_test_from_md(os.path.join(scripts_dir, script), test)
    if ret:
        test.save()
        current_app.logger.critical(f'Update test suite for {script}')
    return test

def update_test_from_md(md_file, test):
    """
    update test cases and variables for the test
    """
    ret = False
    test_cases = []
    variables = {}
    with open(md_file, encoding='utf-8') as f:
        parser = mistune.BlockLexer()
        text = f.read()
        parser.parse(mistune.preprocessing(text))
        for t in parser.tokens:
            if t["type"] == "table":
                table_header = t["header"][0].lower()
                if table_header == 'test case' or table_header == 'test cases':
                    for c in t["cells"]:
                        if not c[0] == '---':
                            test_cases.append(c[0])
                            break
                if table_header == 'variable' or table_header == 'variables':
                    list_var = None
                    for c in t["cells"]:
                        if c[0].startswith('#') or c[0].startswith('---'):
                            continue
                        if c[0].startswith('${'):
                            list_var = None
                            dict_var = None
                            variables[filter_kw(c[0])] = c[1]
                        elif c[0].startswith('@'):
                            dict_var = None
                            list_var = filter_kw(c[0])
                            variables[list_var] = c[1:]
                        elif c[0].startswith('...'):
                            if list_var:
                                variables[list_var].extend(c[1:])
                            elif dict_var:
                                for i in c[1:]:
                                    if not i:
                                        continue
                                    k, v = i.split('=')
                                    variables[dict_var][k] = v
                        elif c[0].startswith('&'):
                            list_var = None
                            dict_var = filter_kw(c[0])
                            variables[dict_var] = {}
                            for i in c[1:]:
                                if not i:
                                    continue
                                k, v = i.split('=')
                                variables[dict_var][k] = v
                        else:
                            current_app.logger.error('Unknown tag: ' + c[0])
    if test.test_cases != test_cases:
        test.test_cases = test_cases
        ret = True
    if test.variables != variables:
        test.variables = variables
        ret = True
    return ret

def find_modules(script):
    modules = []
    with open(script) as f:
        for line in f:
            if line.startswith('#'):
                continue
            m = MODULE_IMPORT(line)
            if m:
                module = m.group('module')
                mods = module.split(',')
                for m in mods:
                    m = m.strip()
                    modules.append(m.split('.', 1)[0])
    return modules

#TODO find deep dependencies
def find_dependencies(script, organization, team, package_type):
    ret = []
    modules = find_modules(script)
    for module in modules:
        tests = Test.objects(organization=organization, team=team)
        for test in tests:
            if test.package and module in test.package.py_packages:
                ret.append((test.package, test.package_version))
                break
    return ret

def find_pkg_dependencies(pypi_root, package, version, organization, team, package_type):
    pkg_file = pypi_root / package.package_name / package.get_package_by_version(version).filename
    requires = get_package_requires(str(pkg_file), organization, team, type='Test Suite')
    deps = [(package, version)]
    if requires:
        for pkg, version in requires:
            deps.extend(find_pkg_dependencies(pypi_root, pkg, version, organization, team, package_type))
    return deps

def get_internal_packages(package_path):
    with zipfile.ZipFile(package_path) as zf:
        packages = (f.split('/', 1)[0] for f in zf.namelist() if not f.startswith('EGG-INFO'))
        packages = set(packages)
        return list(packages)
    return []

def find_local_dependencies(scripts_root, script, organization, team):
    modules = find_modules(os.path.join(scripts_root, script))
    modules_dep = modules[:]
    ret = [os.path.splitext(script)[0].split('/', 1)[0]]
    for module in modules:
        tests = Test.objects(organization=organization, team=team)
        for test in tests:
            if test.package and module in test.package.py_packages:
                modules_dep.remove(module)
    for f in os.listdir(scripts_root):
        for module in modules_dep:
            f = os.path.splitext(f)[0]
            if f == module:
                ret.append(f)
    return ret

def repack_package(pypi_root, scripts_root, package, pkg_version, dest_root):
    unpack_root = os.path.join(dest_root, 'unpack')
    if os.path.exists(unpack_root):
        shutil.rmtree(unpack_root)
    package_file = package.get_package_by_version(pkg_version)
    pkg_file = pypi_root / package.package_name / package_file.filename
    with zipfile.ZipFile(pkg_file) as zf:
        zf.extractall(unpack_root)
    for py_pkg in package.py_packages:
        ret = dir_util.copy_tree(os.path.join(scripts_root, py_pkg), os.path.join(unpack_root, py_pkg))
    pkg_file = os.path.join(dest_root, package_file.filename)
    with zipfile.ZipFile(pkg_file, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(unpack_root):
            for f in files:
                zf.write(os.path.join(root, f), arcname=os.path.join(root[len(unpack_root):], f))
    return pkg_file

def generate_setup(src_dir, dst_dir, dependencies, project_name, version):
    packages = []
    py_modules = []

    for f in dependencies:
        src = os.path.join(src_dir, f)
        if os.path.isdir(src):
            packages.append(f)
            shutil.copytree(src, os.path.join(dst_dir, f))
        else:
            py_modules.append(f)
            shutil.copy(src + '.py', dst_dir)
    with open(os.path.join(dst_dir, 'setup.py'), 'w') as file:
        file.write(
            "from setuptools import setup\n"
            "setup(name=%r, version=%r, packages=%r, py_modules=%r)\n"
            % (project_name, version, packages, py_modules)
        )
    # with open(os.path.join(dst_dir, 'setup.py')) as file:
    #     print(file.read())
