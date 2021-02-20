import asyncio
import datetime
import re
import time
from urllib.parse import urlparse
from marshmallow import missing
from async_property import async_property
from pkg_resources import parse_version

import jwt
from sanic.log import logger
from umongo import Document, Instance, fields, validate
# from umongo.framework import MotorAsyncIOInstance
from umongo.fields import (BooleanField, DateTimeField, DictField, EmailField,
                           FloatField, IntField, ListField, ReferenceField,
                           StringField, URLField, UUIDField)

from app import app
from app import bcrypt
from app.main.config import key

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

LOCK_TIMEOUT = 20

instance = Instance(app.config.db)

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

@instance.register
class Organization(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    name = StringField(validate=validate.Length(max=50), required=True)
    fullname = StringField(validate=validate.Length(max=100))
    email = EmailField()
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    teams = ListField(ReferenceField('Team'), default=[])
    introduction = StringField(validate=validate.Length(max=500))
    website = URLField()
    owner = ReferenceField('User')
    members = ListField(ReferenceField('User'), default=[])
    editors = ListField(ReferenceField('User'), default=[])
    region = StringField()
    avatar = StringField(validate=validate.Length(max=100))
    path = StringField()
    personal = BooleanField(default=False)

    class Meta:
        collection_name = 'organizations'

@instance.register
class Team(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    name = StringField(validate=validate.Length(max=100), required=True)
    email = EmailField()
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    owner = ReferenceField('User')
    members = ListField(ReferenceField('User'), default=[])
    editors = ListField(ReferenceField('User'), default=[])
    introduction = StringField(validate=validate.Length(max=500))
    avatar = StringField(validate=validate.Length(max=100))
    organization = ReferenceField('Organization')
    path = StringField()

    class Meta:
        collection_name = 'teams'

@instance.register
class User(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    email = EmailField(required=True, unique=True)
    registered_on = DateTimeField(default=datetime.datetime.utcnow)
    name = StringField(validate=validate.Length(max=50))
    password_hash = StringField(validate=validate.Length(max=100))
    roles = ListField(StringField(validate=validate.Length(max=50)))
    avatar = StringField(validate=validate.Length(max=100))
    introduction = StringField(validate=validate.Length(max=500))
    organizations = ListField(ReferenceField('Organization'), default=[])
    teams = ListField(ReferenceField('Team'), default=[])
    region = StringField()

    class Meta:
        collection_name = 'users'

    @property
    def password(self):
        raise AttributeError('password: write-only field')

    @password.setter
    def password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

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
            logger.exception(e)
            return None

    @staticmethod
    async def decode_auth_token(auth_token):
        """
        Decodes the auth token
        :param auth_token:
        :return: dict|string
        """
        try:
            payload = jwt.decode(auth_token, key)
            is_blacklisted_token = await BlacklistToken.check_blacklist(auth_token)
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

@instance.register
class BlacklistToken(Document):
    """
    Token Model for storing JWT tokens
    """
    token = StringField(validate=validate.Length(max=500), required=True, unique=True)
    blacklisted_on = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        collection_name = 'blacklist_tokens'

    def __repr__(self):
        return '<id: token: {}'.format(self.token)

    @staticmethod
    async def check_blacklist(auth_token):
        # check whether auth token has been blacklisted
        res = await BlacklistToken.find_one({'token': str(auth_token)})
        if res is None:
            return False
        return True

@instance.register
class Test(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    test_suite = StringField(validate=validate.Length(max=100), required=True)
    test_cases = ListField(StringField(validate=validate.Length(max=100)))
    variables = DictField()
    path = StringField(validate=validate.Length(max=300), default='')
    author = ReferenceField('User')
    create_date = DateTimeField()
    update_date = DateTimeField()
    organization = ReferenceField('Organization')
    team = ReferenceField('Team')
    staled = BooleanField(default=False)
    package = ReferenceField('Package')
    package_version = StringField()

    class Meta:
        collection_name = 'tests'

    def __eq__(self, other):
        for key, value in self.items():
            if key == 'id':
                continue
            if key == 'create_date' or key == 'update_date':
                continue
            if value != other[key]:
                # missing is substituted to None in __getitem__, ie. other[key]
                if value is missing and other[key] is None:
                    continue
                return False
        return True

    def __hash__(self):
        return hash(str(self.pk))

@instance.register
class Task(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    test = ReferenceField('Test')
    test_suite = StringField(validate=validate.Length(max=100))  # embedded document from Test
    testcases = ListField(StringField())
    schedule_date = DateTimeField(default=datetime.datetime.utcnow)
    run_date = DateTimeField()
    status = StringField(validate=validate.Length(max=50), default='waiting')
    comment = StringField(validate=validate.Length(max=1000))
    kickedoff = IntField(validate=validate.Range(min=0), default=0)
    endpoint_list = ListField(UUIDField())
    parallelization = BooleanField(default=False)
    endpoint_run = ReferenceField('Endpoint')
    priority = IntField(validate=validate.Range(min=QUEUE_PRIORITY_MIN, max=QUEUE_PRIORITY_MAX), default=QUEUE_PRIORITY_DEFAULT)
    variables = DictField()
    tester = ReferenceField('User')
    upload_dir = StringField(validate=validate.Length(max=100))
    test_results = ListField(ReferenceField('TestResult'))
    organization = ReferenceField('Organization') # embedded document from Test
    team = ReferenceField('Team') # embedded document from Test

    class Meta:
        collection_name = 'tasks'

@instance.register
class Endpoint(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    name = StringField(validate=validate.Length(max=100))
    tests = ListField(ReferenceField('Test'))
    status = StringField(default='Offline', validate=validate.Length(max=20))
    enable = BooleanField(default=True)
    last_run_date = DateTimeField()
    organization = ReferenceField('Organization')
    team = ReferenceField('Team')
    uid = UUIDField()

    class Meta:
        collection_name = 'endpoints'

@instance.register
class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    priority = IntField(validate=validate.Range(min=QUEUE_PRIORITY_MIN, max=QUEUE_PRIORITY_MAX), default=QUEUE_PRIORITY_DEFAULT)
    tasks = ListField(ReferenceField('Task'), default=[])
    endpoint = ReferenceField('Endpoint')
    running_task = ReferenceField('Task', allow_none=True, default=missing)
    rw_lock = BooleanField(default=False)
    organization = ReferenceField('Organization')
    team = ReferenceField('Team')
    to_delete = BooleanField(default=False)

    class Meta:
        collection_name = 'task_queues'

    async def acquire_lock(self):
        for i in range(LOCK_TIMEOUT):
            if await self.collection.find_one_and_update({'_id': self.pk, 'rw_lock': False}, {'$set': {'rw_lock': True}}):
                return True
            await asyncio.sleep(0.1)
        else:
            return False

    async def release_lock(self):
        await self.collection.find_one_and_update({'_id': self.pk}, {'$set': {'rw_lock': False}})

    async def pop(self):
        if not await self.acquire_lock():
            return None
        await self.reload()
        if len(self.tasks) == 0:
            await self.release_lock()
            return None
        task = self.tasks.pop(0)
        task = await task.fetch()
        self.running_task = task
        await self.commit()
        await self.release_lock()
        return task

    async def push(self, task):
        if not await self.acquire_lock():
            raise RuntimeError('failed to acquire queue lock')
        self.tasks.append(task)
        await self.commit()
        await self.release_lock()
    
    async def flush(self, cancelled=False):
        if not await self.acquire_lock():
            raise RuntimeError('failed to acquire queue lock')
        if cancelled:
            for task in self.tasks:
                task.status = 'cancelled'
                await task.commit()
        self.tasks = []
        await self.commit()
        await self.release_lock()
        return True

@instance.register
class TestResult(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    test_case = StringField(validate=validate.Length(max=100), required=True)
    test_site = StringField(validate=validate.Length(max=50))
    task = ReferenceField('Task')
    test_date = DateTimeField(default=datetime.datetime.utcnow)
    duration = IntField()
    summary = StringField(validate=validate.Length(max=200))
    status = StringField(validate=validate.Length(max=10), default='FAIL')
    more_result = DictField()

    class Meta:
        collection_name = 'test_results'

@instance.register
class Event(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    code = IntField(required=True)
    message = DictField()
    organization = ReferenceField('Organization', required=True)
    team = ReferenceField('Team', default=None)
    status = StringField(validate=validate.Length(max=10), default='Triggered')
    date = DateTimeField(default=datetime.datetime.utcnow)

    class Meta:
        collection_name = 'events'

@instance.register
class EventQueue(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    events = ListField(ReferenceField('Event'), default=[])
    rw_lock = BooleanField(default=False)

    class Meta:
        collection_name = 'event_queues'

    async def acquire_lock(self):
        for i in range(LOCK_TIMEOUT):
            if await self.collection.find_one_and_update({'_id': self.pk, 'rw_lock': False}, {'$set': {'rw_lock': True}}):
                return True
            await asyncio.sleep(0.1)
        else:
            return False

    async def release_lock(self):
        await self.collection.find_one_and_update({'_id': self.pk}, {'$set': {'rw_lock': False}})

    async def pop(self):
        if not await self.acquire_lock():
            return None
        await self.reload()
        if len(self.events) == 0:
            await self.release_lock()
            return None
        event = self.events.pop(0)
        event = await event.fetch()
        await self.commit()
        await self.release_lock()
        return event

    async def push(self, event):
        if not await self.acquire_lock():
            raise RuntimeError('failed to acquire queue lock')
        self.events.append(event)
        await self.commit()
        await self.release_lock()
    
    async def flush(self, cancelled=False):
        if not await self.acquire_lock():
            raise RuntimeError('failed to acquire queue lock')
        if cancelled:
            for event in self.events:
                event.status = 'Cancelled'
                await event.commit()
        self.events = []
        await self.commit()
        await self.release_lock()
        return True

@instance.register
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

    class Meta:
        collection_name = 'package_files'

@instance.register
class Package(Document):
    schema_version = StringField(validate=validate.Length(max=10), default='1')
    package_type = StringField(required=True)
    name = StringField(required=True)
    index_url = URLField(default='http://127.0.0.1:5000/pypi')
    files = ListField(ReferenceField(PackageFile), default=[])
    proprietary = BooleanField(default=True)
    description = StringField()
    long_description = StringField()
    rating = FloatField(default=4)
    rating_times = IntField(default=1)
    download_times = IntField(default=0)
    organization = ReferenceField('Organization')
    team = ReferenceField('Team')
    uploader = ReferenceField('User')
    py_packages = ListField(StringField(), default=[])  # python packages defined by the test package
    upload_date = DateTimeField()
    modified = BooleanField(default=False)

    version_re = re.compile(r"^(?P<name>.+?)(-(?P<ver>\d.+?))-.*$").match

    class Meta:
        collection_name = 'packages'

    async def get_package_by_version(self, version=None):
        if version is None and len(self.files) > 0:
            return await self.files[0].fetch()
        for f in self.files:
            f = await f.fetch()
            if f.version == version:
                return f
        return None

    @async_property
    async def versions(self):
        return [(await f.fetch()).version for f in self.files]

    async def sort(self):
        files = [await f.fetch() for f in self.files]
        versions = [f.version for f in files]
        pairs = [(f, v) for f, v in zip(files, versions)]
        pairs.sort(key=lambda x: parse_version(x[1]), reverse=True)
        self.files = [f for f, v in pairs]
        await self.commit()

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
        return hash(str(self.pk))

    def __repr__(self):
        return self.package_name

@instance.register
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

    class Meta:
        collection_name = 'documents'

# def register_all(db):
#     instance = Instance(db)
#     instance.register(Organization)
#     instance.register(Team)
#     instance.register(User)
#     instance.register(BlacklistToken)
#     instance.register(Test)
#     instance.register(Task)
#     instance.register(Endpoint)
#     instance.register(TaskQueue)
#     instance.register(TestResult)
#     instance.register(Event)
#     instance.register(EventQueue)
#     instance.register(PackageFile)
#     instance.register(Package)
#     instance.register(Documentation)
