import os
from app.main.config import get_config
from pathlib import Path

from ..model.database import *
from .errors import *

USERS_ROOT = Path(get_config().USERS_ROOT)
BACKING_SCRIPT_ROOT = Path(get_config().BACKING_SCRIPT_ROOT)
UPLOAD_DIR = Path(get_config().UPLOAD_ROOT)
try:
    os.mkdir(UPLOAD_DIR)
except FileExistsError:
    pass


def parse_organization_team(user, data):
    organization = None
    team = None

    owner = User.objects(pk=user['user_id']).first()
    if not owner:
        return error_message(ENOENT, 'User not found'), 404

    org_id = data.get('organization', None)
    team_id = data.get('team', None)
    if team_id:
        team = Team.objects(pk=team_id).first()
        if not team:
            return error_message(ENOENT, 'Team not found'), 404
        if team not in owner.teams:
            return error_message(EINVAL, 'Field organization_team is incorrect, not a team member joined'), 400
    if org_id:
        organization = Organization.objects(pk=org_id).first()
        if not organization:
            return error_message(ENOENT, 'Organization not found'), 404
        if organization not in owner.organizations:
            return error_message(EINVAL, 'Field organization_team is incorrect, not a organization member joined'), 400

    if not organization:
        return error_message(EINVAL, 'Please select an organization/team first'), 400

    return owner, team, organization

def get_test_result_root(task):
    result_dir = USERS_ROOT / task.organization.path
    if task.team:
        result_dir = result_dir / task.team.name
    result_dir = result_dir / 'test_results' / str(task.id)
    return result_dir

def get_backing_scripts_root(task):
    result_dir = USERS_ROOT / task.organization.path
    if task.team:
        result_dir = result_dir / task.team.name
    result_dir = result_dir / BACKING_SCRIPT_ROOT
    return result_dir

def get_upload_files_root(task):
    return UPLOAD_DIR / task.upload_dir
