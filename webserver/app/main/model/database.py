import datetime
import time
import jwt
import re

from flask import current_app
from .. import flask_bcrypt
from ..config import key
from mongoengine import Document, StringField, EmailField, ListField, ReferenceField, DateTimeField, DictField, URLField, BooleanField, IntField, UUIDField, FloatField
from urllib.parse import urlparse

QUEUE_PRIORITY_MIN = 1
QUEUE_PRIORITY_DEFAULT = 2
QUEUE_PRIORITY_MAX = 3
QUEUE_PRIORITY = (QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MIN)

EVENT_CODE_START_TASK = 200
EVENT_CODE_CANCEL_TASK = 201
EVENT_CODE_UPDATE_USER_SCRIPT = 202
EVENT_CODE_TASKQUEUE_START = 203
EVENT_CODE_TASKQUEUE_UPDATE = 204
EVENT_CODE_TASKQUEUE_DELETE = 205
EVENT_CODE_EXIT_EVENT_TASK = 206
EVENT_CODE_DELETE_ENDPOINT = 207
EVENT_CODE_GET_ENDPOINT_CONFIG = 208

LOCK_TIMEOUT = 50

class IPAddressField(StringField):
    """A field that validates input as an IP address, may including port.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def validate(self, value):
        try:
            urlparse(value)
        except ValueError:
            self.error(u"Invalid IP address: {}".format(value))

class Organization(Document):
    schema_version = StringField(max_length=10, default='1')
    name = StringField(max_length=50, required=True)
    fullname = StringField(max_length=100)
    email = EmailField()
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    teams = ListField(ReferenceField('Team'))
    introduction = StringField(max_length=500)
    website = URLField()
    owner = ReferenceField('User')
    members = ListField(ReferenceField('User'))
    editors = ListField(ReferenceField('User'))
    region = StringField()
    avatar = StringField(max_length=100)
    path = StringField()
    personal = BooleanField(default=False)

    meta = {'collection': 'organizations'}

class Team(Document):
    schema_version = StringField(max_length=10, default='1')
    name = StringField(max_length=100, required=True)
    email = EmailField()
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    owner = ReferenceField('User')
    members = ListField(ReferenceField('User'))
    editors = ListField(ReferenceField('User'))
    introduction = StringField(max_length=500)
    avatar = StringField(max_length=100)
    organization = ReferenceField(Organization)
    path = StringField()

    meta = {'collection': 'teams'}

class User(Document):
    schema_version = StringField(max_length=10, default='1')
    email = EmailField(required=True, unique=True)
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    name = StringField(max_length=50)
    password_hash = StringField(max_length=100)
    roles = ListField(StringField(max_length=50))
    avatar = StringField(max_length=100)
    introduction = StringField(max_length=500)
    organizations = ListField(ReferenceField(Organization))
    teams = ListField(ReferenceField(Team))
    region = StringField()

    meta = {'collection': 'users'}

    @property
    def password(self):
        raise AttributeError('password: write-only field')

    @password.setter
    def password(self, password):
        self.password_hash = flask_bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return flask_bcrypt.check_password_hash(self.password_hash, password)

    @staticmethod
    def encode_auth_token(user_id):
        """
        Generates the Auth Token
        :return: string
        """
        try:
            payload = {
                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1, seconds=5),
                'iat': datetime.datetime.utcnow(),
                'sub': user_id
            }
            return jwt.encode(
                payload,
                key,
                algorithm='HS256'
            )
        except Exception as e:
            current_app.logger.exception(e)
            return None

    @staticmethod
    def decode_auth_token(auth_token):
        """
        Decodes the auth token
        :param auth_token:
        :return: dict|string
        """
        try:
            payload = jwt.decode(auth_token, key)
            is_blacklisted_token = BlacklistToken.check_blacklist(auth_token)
            if is_blacklisted_token:
                return 'Token blacklisted. Please log in again.'
            else:
                return payload
        except jwt.ExpiredSignatureError:
            return 'Signature expired. Please log in again.'
        except jwt.InvalidTokenError:
            return 'Invalid token. Please log in again.'

    def is_collaborator(self):
        return 'collaborator' in self.roles

    def is_admin(self):
        return 'admin' in self.roles

    def __repr__(self):
        return "<User '{}'>".format(self.name)

class BlacklistToken(Document):
    """
    Token Model for storing JWT tokens
    """
    token = StringField(max_length=500, required=True, unique=True)
    blacklisted_on = DateTimeField(default=datetime.datetime.utcnow)

    meta = {'collection': 'blacklist_tokens'}

    def __repr__(self):
        return '<id: token: {}'.format(self.token)

    @staticmethod
    def check_blacklist(auth_token):
        # check whether auth token has been blacklisted
        try:
            res = BlacklistToken.objects(token=str(auth_token)).get()
        except BlacklistToken.DoesNotExist:
            return False
        except BlacklistToken.MultipleObjectsReturned:
            return True
        else:
            return True

class Test(Document):
    schema_version = StringField(max_length=10, default='1')
    test_suite = StringField(max_length=100, required=True)
    test_cases = ListField(StringField(max_length=100))
    variables = DictField()
    path = StringField(max_length=300, default='')
    author = ReferenceField(User)
    create_date = DateTimeField()
    update_date = DateTimeField()
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    staled = BooleanField(default=False)
    package = ReferenceField('Package')
    package_version = StringField()

    meta = {'collection': 'tests'}

    def __eq__(self, other):
        for item in self:
            if item == 'id':
                continue
            if item == 'create_date' or item == 'update_date':
                continue
            if self[item] != other[item]:
                return False
        return True

    def __hash__(self):
        return hash(self.id)

class Task(Document):
    schema_version = StringField(max_length=10, default='1')
    test = ReferenceField(Test)
    test_suite = StringField(max_length=100)  # embedded document from Test
    testcases = ListField(StringField())
    schedule_date = DateTimeField(default=datetime.datetime.utcnow)
    run_date = DateTimeField()
    status = StringField(max_length=50, default='waiting')
    comment = StringField(max_length=1000)
    kickedoff = IntField(min_value=0, default=0)
    endpoint_list = ListField(UUIDField(binary=False))
    parallelization = BooleanField(default=False)
    endpoint_run = ReferenceField('Endpoint')
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    variables = DictField()
    tester = ReferenceField(User)
    upload_dir = StringField(max_length=100)
    test_results = ListField(ReferenceField('TestResult'))
    organization = ReferenceField(Organization) # embedded document from Test
    team = ReferenceField(Team) # embedded document from Test

    meta = {'collection': 'tasks'}

class Endpoint(Document):
    schema_version = StringField(max_length=10, default='1')
    name = StringField(max_length=100)
    tests = ListField(ReferenceField(Test))
    status = StringField(default='Unauthorized', max_length=20)
    enable = BooleanField(default=True)
    last_run_date = DateTimeField()
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    uid = UUIDField(binary=False)

    meta = {'collection': 'endpoints'}

class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    tasks = ListField(ReferenceField(Task))
    endpoint = ReferenceField(Endpoint)
    running_task = ReferenceField(Task)
    rw_lock = BooleanField(default=False)
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    to_delete = BooleanField(default=False)

    meta = {'collection': 'task_queues'}

    def acquire_lock(self):
        for i in range(LOCK_TIMEOUT):
            ret = self.modify({'rw_lock': False}, rw_lock=True)
            if ret:
                return True
            time.sleep(0.1)
        else:
            return False

    def release_lock(self):
        self.modify(rw_lock=False)

    def pop(self):
        if not self.acquire_lock():
            return None
        if 'tasks' not in self or len(self.tasks) == 0:
            task = None
        else:
            task = self.tasks[0]
        self.modify(pop__tasks=-1)
        self.modify(running_task=task)
        self.release_lock()
        return task

    def push(self, task):
        return self.modify(push__tasks=task)
    
    def flush(self, cancelled=False):
        if not self.acquire_lock():
            return False
        if cancelled:
            for task in self.tasks:
                task.update(status='cancelled')
        self.tasks = []
        self.save()
        self.release_lock()
        return True

class TestResult(Document):
    schema_version = StringField(max_length=10, default='1')
    test_case = StringField(max_length=100, required=True)
    test_site = StringField(max_length=50)
    task = ReferenceField(Task)
    test_date = DateTimeField(default=datetime.datetime.utcnow)
    duration = IntField()
    summary = StringField(max_length=200)
    status = StringField(max_length=10, default='FAIL')
    more_result = DictField()

    meta = {'collection': 'test_results'}

class Event(Document):
    schema_version = StringField(max_length=10, default='1')
    code = IntField(required=True)
    message = DictField()
    organization = ReferenceField(Organization, required=True)
    team = ReferenceField(Team)
    status = StringField(max_length=10, default='Triggered')
    date = DateTimeField(default=datetime.datetime.utcnow)

    meta = {'collection': 'events'}

class EventQueue(Document):
    schema_version = StringField(max_length=10, default='1')
    events = ListField(ReferenceField(Event))
    rw_lock = BooleanField(default=False)

    meta = {'collection': 'event_queues'}

    def acquire_lock(self):
        for i in range(LOCK_TIMEOUT):
            ret = self.modify({'rw_lock': False}, rw_lock=True)
            if ret:
                return True
            time.sleep(0.1)
        else:
            return False

    def release_lock(self):
        self.modify(rw_lock=False)

    def pop(self):
        if not self.acquire_lock():
            return None
        if 'events' not in self or len(self.events) == 0:
            event = None
        else:
            event = self.events[0]
        self.modify(pop__events=-1)
        self.release_lock()
        return event

    def push(self, event):
        return self.modify(push__events=event)
    
    def flush(self, cancelled=False):
        if not self.acquire_lock():
            return False
        if cancelled:
            for event in self.events:
                event.update(status='Cancelled')
        self.events = []
        self.save()
        self.release_lock()
        return True

class PackageFile(Document):
    schema_version = StringField(max_length=10, default='1')
    filename = StringField(required=True)
    name = StringField(required=True)
    description = StringField()
    long_description = StringField()
    uploader = ReferenceField(User)
    upload_date = DateTimeField()
    download_times = IntField(default=0)
    version = StringField(default='0.0.1')

    meta = {'collection': 'package_files'}

class Package(Document):
    schema_version = StringField(max_length=10, default='1')
    package_type = StringField(required=True)
    name = StringField(required=True)
    index_url = URLField(default='http://127.0.0.1:5000/pypi')
    files = ListField(ReferenceField(PackageFile))
    proprietary = BooleanField(default=True)
    description = StringField()
    long_description = StringField()
    rating = FloatField(default=4)
    rating_times = IntField(default=1)
    download_times = IntField(default=0)
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    uploader = ReferenceField(User)
    py_packages = ListField(StringField())  # python packages defined by the test package
    upload_date = DateTimeField()
    modified = BooleanField(default=False)

    version_re = re.compile(r"^(?P<name>.+?)(-(?P<ver>\d.+?))-.*$").match

    meta = {'collection': 'packages'}

    def get_package_by_version(self, version=None):
        if version is None and len(self.files) > 0:
            return self.files[0]
        for f in self.files:
            if f.version == version:
                return f
        return None

    @property
    def versions(self):
        return [f.version for f in self.files]

    @property
    def stars(self):
        return round(self.rating)

    @property
    def package_name(self):
        return self.name.replace('-', '_').replace(' ', '_')

    @property
    def latest_version(self):
        if len(self.files) > 0:
            return self.files[0].version
        return None

    def __hash__(self):
        return hash(str(self.id))

    def __repr__(self):
        return self.package_name

class Documentation(Document):
    schema_version = StringField(max_length=10, default='1')
    filename = StringField(required=True)
    path = StringField(required=True)
    uploader = ReferenceField(User)
    upload_date = DateTimeField(default=datetime.datetime.utcnow)
    last_modifier = ReferenceField(User)
    last_modified = DateTimeField(default=datetime.datetime.utcnow)
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    view_times = IntField(default=0)
    proprietary = BooleanField(default=False)
    locked = BooleanField(default=False)
    language = StringField(default='en')

    meta = {'collection': 'documents'}
