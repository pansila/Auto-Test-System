from flask_restplus import Namespace, fields


class UserDto:
    api = Namespace('user', description='user related operations')
    user = api.model('user', {
        'email': fields.String(required=True, description='user email address'),
        'username': fields.String(required=True, description='user username'),
        'password': fields.String(required=True, description='user password'),
        'public_id': fields.String(description='user Identifier')
    })


class AuthDto:
    api = Namespace('auth', description='authentication related operations')
    user_auth = api.model('auth_details', {
        'email': fields.String(required=True, description='The email address'),
        'username': fields.String(required=False, description='user username'),
        'password': fields.String(required=True, description='The user password '),
    })

class TestDto:
    api = Namespace('test', description='test management operations')
    user = api.model('test', {
        'test': fields.String(required=True, description='test'),
    })

class TaskDto:
    api = Namespace('task', description='task management operations')
    user = api.model('task', {
        'test': fields.String(required=True, description='test'),
    })

class TestResultDto:
    api = Namespace('testresult', description='serve test result files')
    user = api.model('testresult', {
        'test': fields.String(required=True, description='test'),
    })

class TaskResourceDto:
    api = Namespace('taskresource', description='task resources')
    user = api.model('taskresource', {
        'test': fields.String(required=True, description='test'),
    })

class EndpointDto:
    api = Namespace('endpoint', description='test endpoint management operations')
    user = api.model('endpoint', {
        'test': fields.String(required=True, description='test'),
    })

class ScriptDto:
    api = Namespace('script', description='scripts management operations')
    user = api.model('script', {
        'test': fields.String(required=True, description='test'),
    })
