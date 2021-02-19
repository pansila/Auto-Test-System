import os
from sanic.log import logger
from app import app
from pathlib import Path

from ..model.database import *
from .response import *

TEST_RESULTS_ROOT = 'test_results'
USER_SCRIPT_ROOT = 'user_scripts'
BACK_SCRIPT_ROOT = 'back_scripts'
TEST_PACKAGE_ROOT = 'pypi'
USER_DOCUMENT_ROOT = 'document'
USER_PICTURE_ROOT = 'pictures'
USERS_ROOT = Path(app.config['USERS_ROOT'])
UPLOAD_ROOT = Path(app.config['UPLOAD_ROOT'])
STORE_ROOT = Path(app.config['STORE_ROOT'])
DOCUMENT_ROOT = Path(app.config['DOCUMENT_ROOT'])
PICTURE_ROOT = Path(app.config['PICTURE_ROOT'])

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
USERS_ROOT.mkdir(parents=True, exist_ok=True)
STORE_ROOT.mkdir(parents=True, exist_ok=True)
DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True)
PICTURE_ROOT.mkdir(parents=True, exist_ok=True)


async def get_test_result_path(task):
    return await get_test_results_root(task) / str(task.pk)

async def get_test_results_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            logger.error('team or organization should not used along wite task')
            return None
        organization = await task.organization.fetch()
        team = None
        if task.team:
            team = await task.team.fetch()

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / TEST_RESULTS_ROOT
    return result_dir

async def get_back_scripts_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            logger.error('team or organization should not used along wite task')
            return None
        organization = await task.organization.fetch()
        team = None
        if task.team:
            team = await task.team.fetch()

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / BACK_SCRIPT_ROOT
    return result_dir

async def get_user_scripts_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            logger.error('team or organization should not used along wite task')
            return None
        organization = await task.organization.fetch()
        team = None
        if task.team:
            team = await task.team.fetch()

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / USER_SCRIPT_ROOT
    return result_dir

def get_upload_files_root(task):
    return UPLOAD_ROOT / task.upload_dir

async def get_test_store_root(task=None, proprietary=False, team=None, organization=None):
    if task:
        organization = await task.organization.fetch()
        team = None
        if task.team:
            team = await task.team.fetch()
        test = await task.test.fetch()
        package = await test.package.fetch()
        proprietary = package.proprietary if test.package else False

    if not proprietary or (not team and not organization):
        return STORE_ROOT

    store_dir = USERS_ROOT / organization.path
    if team:
        store_dir = store_dir / team.path
    store_dir = store_dir / TEST_PACKAGE_ROOT
    return store_dir

def is_path_secure(path):
    if not isinstance(path, Path):
        path = Path(path)
    if path.is_reserved():
        return False
    for part in path.as_posix().split('/'):
        if part == os.path.pardir:
            return False
    root = path.root
    if root == '\\' or root == '/':
        return False
    return True

def get_document_root(language='en', organization=None, team=None):
    if not organization:
        if team:
            organization = team.organization
        else:
            return DOCUMENT_ROOT / language
    doc_dir = USERS_ROOT / organization.path
    if team:
        doc_dir = doc_dir / team.path
    doc_dir = doc_dir / USER_DOCUMENT_ROOT / language
    return doc_dir

def get_pictures_root(language='en', organization=None, team=None):
    if not organization:
        if team:
            organization = team.organization
        else:
            return PICTURE_ROOT / language
    doc_dir = USERS_ROOT / organization.path
    if team:
        doc_dir = doc_dir / team.path
    doc_dir = doc_dir / USER_PICTURE_ROOT / language
    return doc_dir
