from mongoengine import *
from mongoengine.connection import disconnect
import datetime


QUEUE_PRIORITY_MIN = 1
QUEUE_PRIORITY_DEFAULT = 2
QUEUE_PRIORITY_MAX = 3

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

    @classmethod
    def get_list(cls):
        test_suites = cls.objects({})
        return [t.test_suite for t in test_suites]


class Task(Document):
    schema_version = StringField(max_length=10, default='1')
    test = ReferenceField(Test)
    testcases = ListField(StringField())
    start_date = DateTimeField(default=datetime.datetime.utcnow)
    run_date = DateTimeField(default=datetime.datetime.utcnow)
    status = StringField(default='waiting')
    kickedoff = IntField(min_value=0, default=0)
    endpoint_list = ListField(StringField())
    endpoint_run = StringField()
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    variables = DictField()
    tester = EmailField()
    upload_dir = StringField()

    meta = {'collection': 'tasks'}

class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    endpoint_address = StringField()
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    tasks = ListField(ReferenceField(Task))

    meta = {'collection': 'taskqueues'}

    @classmethod
    def pop(cls, endpoint_address, priority=QUEUE_PRIORITY_DEFAULT):
        '''
        pop from the head of queue
        '''
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(pop__tasks=-1)
        if queue == None or len(queue.tasks) == 0:
            return None
        task = queue.tasks[0]
        return task

    @classmethod
    def push(cls, task, endpoint_address, priority=QUEUE_PRIORITY_DEFAULT):
        '''
        push a task into the tail of queue
        '''
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(new=True, push__tasks=task)
        if queue == None:
            return None
        return queue

    # @classmethod
    # def __getitem__(cls, index, priority=QUEUE_PRIORITY_DEFAULT, endpoint_address):
    #     pass

class TestResult(Document):
    schema_version = StringField(max_length=10, default='1')
    test_case = StringField(max_length=100, required=True)
    test_site = StringField(max_length=50)
    test_suite = ReferenceField(Test)
    tester = StringField(max_length=20)
    tester_email = EmailField()
    test_date = DateTimeField()
    duration = IntField()
    summary = StringField(max_length=200)
    status = StringField(max_length=10, default='Fail')

    meta = {'allow_inheritance': True}

class TaskArchived(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    task_max = IntField(default=100)
    tasks = ListField(ReferenceField(Task))

    meta = {'collection': 'taskarchived'}

class MongoDBClient():

    def __init__(self, config):
        connect('autotest', host=config['mongodb_uri'], port=config['mongodb_port'])
    
    def __del__(self):
        disconnect()
