from mongoengine import *
from mongoengine.connection import disconnect
import datetime


MAX_PRIORITY = 3
MIN_PRIORITY = 1
DEFAULT_PRIORITY = 2

class Test(Document):
    schema_version = StringField(max_length=10, default='1')
    test_suite = StringField(max_length=100, unique=True, required=True)
    test_cases = ListField(StringField(max_length=100))
    parameters = DictField()
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
    task = ReferenceField(Test)
    start_date = DateTimeField(default=datetime.datetime.utcnow)
    run_date = DateTimeField(default=datetime.datetime.utcnow)
    status = StringField(max_length=10, default='Pending')
    endpoint_list = ListField(StringField())
    endpoint_run = StringField()
    priority = IntField(min_value=MIN_PRIORITY, max_value=MAX_PRIORITY, default=DEFAULT_PRIORITY)

    meta = {'collection': 'tasks'}

class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    endpoint_address = StringField()
    priority = IntField(min_value=MIN_PRIORITY, max_value=MAX_PRIORITY, default=DEFAULT_PRIORITY)
    tasks = ListField(ReferenceField(Task))

    meta = {'collection': 'taskqueues'}

    @classmethod
    def pop(cls, endpoint_address, priority=DEFAULT_PRIORITY):
        '''
        pop from the head of queue rather than from tail
        '''
        print(cls.objects())
        queue = cls.objects(priority=priority, endpoint_address=endpoint_address).modify(pop__tasks=-1)
        if queue == None:
            return None
        if len(queue.tasks) == 0:
            return None
        task = queue.tasks[0]
        print(task)
        return task

    # @classmethod
    # def __getitem__(cls, index, priority=DEFAULT_PRIORITY, endpoint_address):
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

class MongoDBClient():

    def __init__(self, config):
        connect('autotest', host=config['mongodb_uri'], port=config['mongodb_port'])
    
    def __del__(self):
        disconnect()
