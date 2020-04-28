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
VERSION_CHECK = re.compile(r'(?P<name>.*?)(?P<compare>\s*(==|>=|<=|!=)\s*)?(?P<version>\d.+?)?$').match
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
def install_test_suite(package, user, organization, team, pypi_root, proprietary, version=None, new_package=True):
    if version is None:
        version = package.latest_version
        pkg_file = package.files[0]
    else:
        pkg_file = package.get_package_by_version(version)
        if not pkg_file:
            current_app.logger.error(f'package file not found for {package.name} with version {version}')
            return False
    pkg_file = pypi_root / package.package_name / pkg_file

    requires = get_package_requires(str(pkg_file), organization, team, type='Test Suite')
    if requires:
        for pkg, ver in requires:
            ret = install_test_suite(pkg, user, organization, team, pypi_root, proprietary, version=ver, new_package=False)
            if not ret:
                current_app.logger.error(f'Failed to install dependent package {package.name}')
                return False

    scripts_root = get_user_scripts_root(organization=organization, team=team)
    libraries_root = get_back_scripts_root(organization=organization, team=team)
    with zipfile.ZipFile(pkg_file) as zf:
        for f in zf.namelist():
            if f.startswith('EGG-INFO'):
                continue
            dirname = os.path.dirname(f)
            if os.path.exists(scripts_root / dirname):
                shutil.rmtree(scripts_root / dirname)
            if os.path.exists(libraries_root / dirname):
                shutil.rmtree(libraries_root / dirname)

    with zipfile.ZipFile(pkg_file) as zf:
        libraries = (f for f in zf.namelist() if not f.startswith('EGG-INFO') and '/scripts/' not in f)
        for l in libraries:
            zf.extract(l, libraries_root)
        scripts = [f for f in zf.namelist() if '/scripts/' in f]
        for s in scripts:
            zf.extract(s, scripts_root)
        for pkg_name in set((s.split('/', 1)[0] for s in scripts)):
            for f in os.listdir(scripts_root / pkg_name / 'scripts'):
                shutil.move(str(scripts_root / pkg_name / 'scripts' / f), scripts_root / pkg_name)
                db_update_test(scripts_root, os.path.join(pkg_name, f), user, organization, team, package, version)
            shutil.rmtree(scripts_root / pkg_name / 'scripts')
    package.modify(inc__download_times=1)
    return True

def db_update_test(scripts_dir, script, user, organization, team, package=None, version=None):
    if scripts_dir is None:
        return False
    if not script.endswith('.md'):
        return False

    basename = os.path.basename(script)
    dirname = os.path.dirname(script)
    test_suite = os.path.splitext(basename)[0]
    test = Test.objects(test_suite=test_suite, path=dirname).first()
    if not test:
        test = Test(path=dirname, author=user, organization=organization, team=team,
                    test_suite=test_suite, package=package, package_version=version)
        test.create_date = datetime.datetime.utcnow()
    else:
        test.modify(package=package, package_version=version)

    ret = update_test_from_md(os.path.join(scripts_dir, script), test)
    if ret:
        test.update_date = datetime.datetime.utcnow()
        test.save()
        current_app.logger.critical(f'Update test suite for {script}')
    return True

def update_test_from_md(md_file, test):
    """
    update test cases and variables for the test
    """
    ret = False
    test_cases = []
    variables = {}
    with open(md_file) as f:
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
    pkg_file = pypi_root / package.package_name / package.get_package_by_version(version)
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
