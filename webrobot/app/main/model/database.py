import datetime
import time
import jwt

from .. import flask_bcrypt
from ..config import key
from mongoengine import *

QUEUE_PRIORITY_MIN = 1
QUEUE_PRIORITY_DEFAULT = 2
QUEUE_PRIORITY_MAX = 3

EVENT_CODE_CANCEL_TASK = 200
EVENT_CODE_UPDATE_USER_SCRIPT = 201
EVENT_CODE_TASKQUEUE_UPDATE = 202
EVENT_CODE_TASKQUEUE_DELETE = 203

LOCK_TIMEOUT = 5

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
    region = StringField()
    avatar = StringField(max_length=100)
    path = StringField()

    meta = {'collection': 'organizations'}

class Team(Document):
    schema_version = StringField(max_length=10, default='1')
    name = StringField(max_length=100, required=True)
    email = EmailField()
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    owner = ReferenceField('User')
    members = ListField(ReferenceField('User'))
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
            print(e)
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
    path = StringField(max_length=300, unique=True)
    author = ReferenceField(User)
    create_date = DateTimeField()
    update_date = DateTimeField()
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)

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
    endpoint_list = ListField(StringField(max_length=50))
    parallelization = BooleanField(default=False)
    endpoint_run = StringField(max_length=50)
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
    endpoint_address = StringField(required=True)
    tests = ListField(ReferenceField(Test))
    status = StringField(default='Offline', max_length=10)
    enable = BooleanField(default=True)
    last_run_date = DateTimeField()
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)

    meta = {'collection': 'endpoints'}

class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    endpoint_address = StringField(max_length=50, required=True)  # embedded document from Endpoint
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    tasks = ListField(ReferenceField(Task))
    endpoint = ReferenceField(Endpoint)
    running_task = ReferenceField(Task)
    rw_lock = BooleanField(default=False)
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    test_alive = BooleanField(default=False)
    to_delete = BooleanField(default=False)

    meta = {'collection': 'task_queues'}

    def acquire_lock(self):
        timeout = 0
        while True:
            ret = self.modify({'rw_lock': False}, rw_lock=True)
            if not ret:
                if timeout >= LOCK_TIMEOUT:
                    return False
                time.sleep(0.1)
                timeout = timeout + 0.1
            else:
                break
        return True

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
        self.release_lock()
        return task

    def push(self, task):
        if not self.acquire_lock():
            return False
        ret = self.modify(push__tasks=task)
        self.release_lock()
        return ret
    
    def flush(self):
        if not self.acquire_lock():
            return False
        self.tasks = []
        self.save()
        self.release_lock()
        return True

    # @classmethod
    # def __getitem__(cls, index, priority=QUEUE_PRIORITY_DEFAULT, endpoint_address):
    #     pass

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

    meta = {'collection': 'events'}

class EventQueue(Document):
    schema_version = StringField(max_length=10, default='1')
    events = ListField(ReferenceField(Event))
    rw_lock = BooleanField(default=False)
    organization = ReferenceField(Organization)
    team = ReferenceField(Team)
    test_alive = BooleanField(default=False)
    to_delete = BooleanField(default=False)

    meta = {'collection': 'event_queues'}

    def acquire_lock(self):
        timeout = 0
        while True:
            ret = self.modify({'rw_lock': False}, rw_lock=True)
            if not ret:
                if timeout >= LOCK_TIMEOUT:
                    return False
                time.sleep(0.1)
                timeout = timeout + 0.1
            else:
                break
        return True

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
        if not self.acquire_lock():
            return False
        ret = self.modify(push__events=event)
        self.release_lock()
        return ret
    
    def flush(self):
        if not self.acquire_lock():
            return False
        self.events = []
        self.save()
        self.release_lock()
        return True
