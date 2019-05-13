import datetime
import time

from mongoengine import *

QUEUE_PRIORITY_MIN = 1
QUEUE_PRIORITY_DEFAULT = 2
QUEUE_PRIORITY_MAX = 3

EVENT_CODE_CANCEL_TASK = 200
EVENT_CODE_UPDATE_USER_SCRIPT = 201

LOCK_TIMEOUT = 5

class Test(Document):
    schema_version = StringField(max_length=10, default='1')
    test_suite = StringField(max_length=100, unique=True, required=True)
    test_cases = ListField(StringField(max_length=100))
    variables = DictField()
    path = StringField(max_length=300)
    author = StringField(max_length=50)
    create_date = DateTimeField()
    update_date = DateTimeField()

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
    tester = EmailField()
    upload_dir = StringField(max_length=100)
    test_results = ListField(ReferenceField('TestResult'))

    meta = {'collection': 'tasks'}

class Endpoint(Document):
    schema_version = StringField(max_length=10, default='1')
    name = StringField(max_length=100)
    endpoint_address = StringField(required=True)
    tests = ListField(ReferenceField(Test))
    status = StringField(default='Offline', max_length=10)
    enable = BooleanField(default=True)
    last_run_date = DateTimeField()

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
    rwLock = BooleanField(default=False)

    meta = {'collection': 'taskqueues'}

    @classmethod
    def acquire_lock(cls, endpoint_address, priority):
        timeout = 0
        while True:
            old = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(rwLock=True)
            if old.rwLock:
                if timeout >= LOCK_TIMEOUT:
                    return False
                time.sleep(0.1)
                timeout = timeout + 0.1
            else:
                break
        return True

    @classmethod
    def release_lock(cls, endpoint_address, priority):
        cls.objects(priority=priority, endpoint_address=endpoint_address).modify(rwLock=False)

    @classmethod
    def pop(cls, endpoint_address, priority=QUEUE_PRIORITY_DEFAULT):
        '''
        pop from the head of queue
        '''
        if not cls.acquire_lock(endpoint_address, priority):
            return None
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(pop__tasks=-1)
        if queue == None or len(queue.tasks) == 0:
            task = None
        else:
            task = queue.tasks[0]
        cls.release_lock(endpoint_address, priority)
        return task

    @classmethod
    def push(cls, task, endpoint_address, priority=QUEUE_PRIORITY_DEFAULT):
        '''
        push a task into the tail of queue
        '''
        if not cls.acquire_lock(endpoint_address, priority):
            return None
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(new=True, push__tasks=task)
        cls.release_lock(endpoint_address, priority)
        return queue
    
    @classmethod
    def flush(cls, endpoint_address, priority):
        if not cls.acquire_lock(endpoint_address, priority):
            return False
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address)
        if queue.count() != 1:
            cls.release_lock(endpoint_address, priority)
            return False
        q = queue[0]
        q.tasks = []
        q.save()
        cls.release_lock(endpoint_address, priority)
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

    meta = {'collection': 'testresults'}

class TaskArchived(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    task_max = IntField(default=100)
    tasks = ListField(ReferenceField(Task))

    meta = {'collection': 'taskarchived'}

class Event(Document):
    schema_version = StringField(max_length=10, default='1')
    code = IntField(required=True)
    message = DictField()

    meta = {'collection': 'events'}

class EventQueue(Document):
    schema_version = StringField(max_length=10, default='1')
    events = ListField(ReferenceField(Event))
    rwLock = BooleanField(default=False)

    meta = {'collection': 'eventqueues'}

    @classmethod
    def acquire_lock(cls):
        timeout = 0
        while True:
            old = cls.objects().modify(rwLock=True)
            if old.rwLock:
                if timeout >= LOCK_TIMEOUT:
                    return False
                time.sleep(0.1)
                timeout = timeout + 0.1
            else:
                break
        return True

    @classmethod
    def release_lock(cls):
        cls.objects().modify(rwLock=False)

    @classmethod
    def pop(cls):
        if not cls.acquire_lock():
            return None
        queue = cls.objects().modify(pop__events=-1)
        if queue == None or len(queue.events) == 0:
            event = None
        else:
            event = queue.events[0]
        cls.release_lock()
        return event

    @classmethod
    def push(cls, event):
        if not cls.acquire_lock():
            return None
        queue = cls.objects().modify(new=True, push__events=event)
        cls.release_lock()
        return queue
    
    @classmethod
    def flush(cls):
        if not cls.acquire_lock():
            return False
        queue = cls.objects()
        if queue.count() != 1:
            cls.release_lock()
            return False
        q = queue[0]
        q.events = []
        q.save()
        cls.release_lock()
        return True
