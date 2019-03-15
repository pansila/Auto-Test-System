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
        'password': fields.String(required=True, description='The user password '),
    })

class ScriptDto:
    api = Namespace('scripts', description='script download interface')
    user = api.model('scripts', {
        'test': fields.String(required=True, description='test'),
    })

class TaskDto:
    api = Namespace('task', description='task management operations')
    user = api.model('task', {
        'test': fields.String(required=True, description='test'),
    })

class TaskQueueDto:
    api = Namespace('taskqueue', description='task management operations')
    user = api.model('taskqueue', {
        'test': fields.String(required=True, description='test'),
    })

class TestResultDto:
    api = Namespace('testresult', description='serve test result files')
    user = api.model('testresult', {
        'test': fields.String(required=True, description='test'),
    })
