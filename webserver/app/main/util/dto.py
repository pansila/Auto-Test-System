from flask_restx import Namespace, fields, Model

# Don't know why it doesn't work sometimes if put these outside DTO classes

# response = Model('response', {
#     'code': fields.Integer(),
#     'message': fields.String(),
# })

# organization_team = Model('organization_team', {
#     'organization': fields.String(required=True, description='The organization id'),
#     'team': fields.String(description='The team id'),
# })

class UserDto:
    api = Namespace('user', description='user related operations')
    response = api.model('response', {
        'code': fields.Integer(),
        'message': fields.String(),
    })
    account = api.model('account', {
        'password': fields.String(),
        'email': fields.String(),
        'username': fields.String(),
        'introduction': fields.String(),
        'region': fields.String(),
    })
    user = api.model('user', {
        'user_id': fields.String(description='User identifier'),
        'email': fields.String(),
        'username': fields.String(),
        'introduction': fields.String(),
        'region': fields.String(),
    })
    user_info = api.inherit('user_info', user, {
        'roles': fields.List(fields.String()),
        'registered_on': fields.DateTime(dt_format='rfc822'),
    })
    user_info_resp = api.inherit('user_info_resp', response, {
        'data': fields.Nested(user_info)
    })
    avatar = api.model('avatar', {
        'type': fields.String()
    })
    password = api.model('password', {
        'password': fields.String()
    })
    password_update = api.model('password_update', {
        'oldPassword': fields.String(),
        'newPassword': fields.String()
    })

class AuthDto:
    api = Namespace('auth', description='authentication related operations')
    user_auth = api.model('auth_details', {
        'email': fields.String(required=True, description='The email address'),
        'password': fields.String(required=True, description='The user password ')
    })

class CertDto:
    api = Namespace('cert', description='certificate/key related operations')
    cert_key = api.model('cert_key', {
        'test': fields.String(description='test'),
    })

class SettingDto:
    api = Namespace('setting', description='settings of the server')

class TestDto:
    api = Namespace('test', description='test management operations')
    test_cases = api.model('test_cases', {
        'test_cases': fields.List(fields.String()),
        'test_suite': fields.String(),
    })
    test_suite = api.model('test_suite', {
        'id': fields.String(),
        'test_suite': fields.String(),
        'path': fields.String(),
        'test_cases': fields.List(fields.String()),
        'variables': fields.Raw(),
        'author': fields.String()
    })

class TaskDto:
    api = Namespace('task', description='task management operations')
    organization_team = api.model('organization_team', {
        'organization': fields.String(required=True, description='The organization id'),
        'team': fields.String(description='The team id'),
    })

    task_id = api.inherit('task_id', organization_team, {
        'task_id': fields.String(required=True, description='The task id'),
    })
    task_update = api.inherit('task_update', task_id, {
        'comment': fields.String(required=True, description='The task comment'),
    })
    task_cancel = api.inherit('task_cancel', task_id, {
        'endpoint_uid': fields.String(description='The endpoint uid that is running the test'),
        'priority': fields.Integer(description='The priority of the task'),
    })
    task_stat = api.model('task_stat', {
        'succeeded': fields.Integer(description='The count of tasks ran successfully in the day'),
        'failed': fields.Integer(description='The count of tasks failed to run in the day'),
        'running': fields.Integer(description='The count of tasks running right now'),
        'waiting': fields.Integer(description='The count of tasks waiting right now'),
    })
    task = api.inherit('task', organization_team, {
        'test_suite': fields.String(required=True, description='The test suite name'),
        'path': fields.String(required=True, description='The test suite\'s path name'),
        'endpoint_list': fields.List(fields.String(description='The endpoints to run the test')),
        'priority': fields.Integer(description='The priority of the task(larger number means higher importance)'),
        'parallelization': fields.Boolean(default=False),
        'variables': fields.List(fields.String()),
        'test_cases': fields.List(fields.String()),
        'upload_dir': fields.String(description='The directory id of the upload files'),
    })

class TestResultDto:
    api = Namespace('testresult', description='serve test result files')
    test_report_summary = api.model('test_report_summary', {
        'id': fields.String(description='The task id'),
        'test_suite': fields.String(description='The test suite name'),
        'testcases': fields.List(fields.String()),
        'comment': fields.String(),
        'priority': fields.Integer(description='The priority of the task'),
        'run_date': fields.DateTime(dt_format='rfc822'),
        'tester': fields.String(),
        'status': fields.String()
    })
    test_report = api.model('test_report', {
        'items': fields.List(fields.Nested(test_report_summary)),
        'total': fields.Integer(),
    })
    task_id = api.model('task_id', {
        'task_id': fields.String(required=True, description='The task id'),
    })
    record_test_result = api.inherit('record_test_result', task_id, {
        'test_case': fields.String(required=True, description='The test case of a test suite'),
    })
    test_result = api.model('test_result', {
        'test_date': fields.DateTime(),
        'duration': fields.Integer(),
        'summary': fields.String(),
        'status': fields.String(default='FAIL'),
        'more_result': fields.Raw()
    })

class TaskResourceDto:
    api = Namespace('taskresource', description='task resources')
    organization_team = api.model('organization_team', {
        'organization': fields.String(required=True, description='The organization id'),
        'team': fields.String(description='The team id'),
    })

    task_id = api.inherit('task_id', organization_team, {
        'task_id': fields.String(required=True, description='The task id'),
    })
    task_resource = api.inherit('task_resource', organization_team, {
        'resource_id': fields.String(description='The directory id to accommodate uploaded files'),
        'retrigger_task': fields.String(description='The task id to retrigger'),
        'file': fields.List(fields.String())
    })

class EndpointDto:
    api = Namespace('endpoint', description='test endpoint management operations')
    organization_team = api.model('organization_team', {
        'organization': fields.String(required=True, description='The organization id'),
        'team': fields.String(description='The team id'),
    })

    endpoint_item = api.model('endpoint_item', {
        'endpoint_uid': fields.String(),
        'name': fields.String(),
        'status': fields.String(),
        'enable': fields.Boolean(),
        'last_run': fields.Integer(description="Timestamp in milliseconds, 0 if not run yet"),
        'tests': fields.List(fields.String()),
        'test_refs': fields.List(fields.String()),
        'endpoint_uid': fields.String()
    })
    endpoint_list = api.model('endpoint_list', {
        'items': fields.List(fields.Nested(endpoint_item)),
        'total': fields.Integer(),
    })
    endpoint_del = api.inherit('endpoint_del', organization_team, {
        'endpoint_uid': fields.String(),
    })
    endpoint = api.inherit('endpoint', organization_team, {
        'endpoint_uid': fields.String(),
        'tests': fields.List(fields.String(), description='The tests that the endpoint supports'),
        'endpoint_name': fields.String(),
        'enable': fields.Boolean(default=False),
    })
    queuing_task = api.model('queuing_task', {
        'endpoint': fields.String(description="The endpoint name"),
        'endpoint_uid': fields.String(description="The endpoint uid"),
        'priority': fields.Integer(),
        'task': fields.String(description="The test name"),
        'task_id': fields.String(description="The task id"),
        'status': fields.String(),
    })
    queuing_tasks = api.model('queuing_tasks', {
        'endpoint_uid': fields.String(description="The endpoint uid"),
        'endpoint': fields.String(description="The endpoint name"),
        'priority': fields.Integer(),
        'waiting': fields.Integer(),
        'status': fields.String(),
        'tasks': fields.List(fields.Nested(queuing_task))
    })
    queue_update = api.inherit('queue_update', organization_team, {
        'taskqueues': fields.List(fields.Nested(queuing_task)),
    })

class ScriptDto:
    api = Namespace('script', description='scripts management operations')
    organization_team = api.model('organization_team', {
        'organization': fields.String(required=True, description='The organization id'),
        'team': fields.String(description='The team id'),
    })

    update_script = api.inherit('update_script', organization_team, {
        'file': fields.String(description='Path to the queried file'),
        'script_type': fields.String(description='File type {test_scripts | test_libraries}'),
        'new_name': fields.String(description='New file name if want to rename'),
        'content': fields.String(description='The file content'),
    })

    delete_script = api.inherit('delete_script', organization_team, {
        'file': fields.String(description='Path to the queried file'),
        'script_type': fields.String(description='File type {test_scripts | test_libraries}'),
    })

    upload_scripts = api.inherit('upload_scripts', organization_team, {
        'script_type': fields.String(description='File type {test_scripts | test_libraries}'),
        'example_file': fields.String(description='Content-Type: application/text')
    })

class OrganizationDto:
    api = Namespace('organization', description='organization management operations')
    organization = api.model('organization', {
        'label': fields.String(description='The organization name'),
        'owner': fields.String(description='The organization owner\'s name'),
        'owner_email': fields.String(description='The organization owner\'s email'),
        'personal': fields.Boolean(description='The organization is of person', default=False),
        'value': fields.String(description='The organization ID'),
    })

    _team = api.model('_team', {
        'label': fields.String(description='The team name'),
        'owner': fields.String(description='The team owner\'s name'),
        'owner_email': fields.String(description='The team owner\'s email'),
        'value': fields.String(description='The team ID'),
    })

    new_organization = api.model('new_organization', {
        'name': fields.String(description='The organization name'),
    })

    organization_id = api.model('organization_id', {
        'organization_id': fields.String(description='The organization ID'),
    })

    # we could have inherited the model organization, but swagger UI has a problem to show it correctly, thus we embed organization definition here.
    organization_team_resp = api.model('organization_team_resp', {
        'label': fields.String(description='The organization name'),
        'owner': fields.String(description='The organization owner\'s name'),
        'owner_email': fields.String(description='The organization owner\'s email'),
        'value': fields.String(description='The organization ID'),
        'children': fields.List(fields.Nested(_team)),
    })

    user = api.model('user', {
        'label': fields.String(description='The user name'),
        'email': fields.String(description='The user email'),
        'value': fields.String(description='The user ID'),
    })

    transfer_ownership = api.inherit('transfer_ownership', organization_id, {
        'new_owner': fields.String(description='The new owner\'s ID'),
    })

class TeamDto:
    api = Namespace('team', description='team management operations')
    team = api.model('team', {
        'label': fields.String(description='The team name'),
        'owner': fields.String(description='The team owner\'s name'),
        'owner_email': fields.String(description='The team owner\'s email'),
        'organization_id': fields.String(description='The ID of the organization that the team belongs to'),
        'value': fields.String(description='The team ID'),
    })

    new_team = api.model('new_team', {
        'name': fields.String(description='The team name'),
        'organization_id': fields.String(description='The organization ID'),
    })

    team_id = api.model('team_id', {
        'team_id': fields.String(description='The team ID'),
    })

    user = api.model('user', {
        'label': fields.String(description='The user name'),
        'email': fields.String(description='The user email'),
        'value': fields.String(description='The user ID'),
    })

class StoreDto:
    api = Namespace('store', description='scripts management operations')
    organization_team = api.model('organization_team', {
        'organization': fields.String(description='The organization id'),
        'team': fields.String(description='The team id'),
    })

    delete_package = api.inherit('delete_package', organization_team, {
        'file': fields.String(description='Path to the queried file'),
    })

    upload_package = api.inherit('upload_package', organization_team, {
        'example_file': fields.String(description='Content-Type: application/text')
    })

class PypiDto:
    api = Namespace('pypi', description='local python package index repository')