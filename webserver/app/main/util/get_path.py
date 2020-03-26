import os
from app.main.config import get_config
from flask import current_app
from pathlib import Path

from ..model.database import *
from .response import *

TEST_RESULTS_ROOT = 'test_results'
USER_SCRIPT_ROOT = 'user_scripts'
BACK_SCRIPT_ROOT = 'back_scripts'
TEST_PACKAGE_ROOT = 'test_packages'
USERS_ROOT = Path(get_config().USERS_ROOT)
UPLOAD_ROOT = Path(get_config().UPLOAD_ROOT)
STORE_ROOT = Path(get_config().STORE_ROOT)
try:
    os.mkdir(UPLOAD_ROOT)
except FileExistsError:
    pass
try:
    os.mkdir(USERS_ROOT)
except FileExistsError:
    pass
try:
    os.mkdir(STORE_ROOT)
except FileExistsError:
    pass

def get_test_result_path(task):
    return get_test_results_root(task) / str(task.id)

def get_test_results_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            current_app.logger.error('team or organization should not used along wite task')
            return None
        organization = task.organization
        team = task.team

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / TEST_RESULTS_ROOT
    return result_dir

def get_back_scripts_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            current_app.logger.error('team or organization should not used along wite task')
            return None
        organization = task.organization
        team = task.team

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / BACK_SCRIPT_ROOT
    return result_dir

def get_user_scripts_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            current_app.logger.error('team or organization should not used along wite task')
            return None
        organization = task.organization
        team = task.team

    result_dir = USERS_ROOT / organization.path
    if team:
        result_dir = result_dir / team.path
    result_dir = result_dir / USER_SCRIPT_ROOT
    return result_dir

def get_upload_files_root(task):
    return UPLOAD_ROOT / task.upload_dir

def get_test_store_root(task=None, team=None, organization=None):
    if task:
        if team or organization:
            current_app.logger.error('team or organization should not used along wite task')
            return None
        organization = task.organization
        team = task.team

    if not organization:
        return STORE_ROOT

    store_dir = USERS_ROOT / organization.path
    if team:
        store_dir = store_dir / team.path
    store_dir = store_dir / TEST_PACKAGE_ROOT
    return store_dir
