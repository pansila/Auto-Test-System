import datetime

from mongoengine import *

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

class Task(Document):
    schema_version = StringField(max_length=10, default='1')
    test = ReferenceField(Test)
    test_suite = StringField()  # embedded document from Test
    testcases = ListField(StringField())
    schedule_date = DateTimeField(default=datetime.datetime.utcnow)
    run_date = DateTimeField()
    status = StringField(default='waiting')
    kickedoff = IntField(min_value=0, default=0)
    endpoint_list = ListField(StringField())
    endpoint_run = StringField()
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    variables = DictField()
    tester = EmailField()
    upload_dir = StringField()
    test_results = ListField(ReferenceField('TestResult'))

    meta = {'collection': 'tasks'}

class Endpoint(Document):
    schema_version = StringField(max_length=10, default='1')
    endpoint_address = StringField(required=True)
    tests = ListField(ReferenceField(Test))

    meta = {'collection': 'endpoints'}

class TaskQueue(Document):
    '''
    Per endpoint per priority queue
    '''
    schema_version = StringField(max_length=10, default='1')
    endpoint_address = StringField(required=True)  # embedded document from Endpoint
    priority = IntField(min_value=QUEUE_PRIORITY_MIN, max_value=QUEUE_PRIORITY_MAX, default=QUEUE_PRIORITY_DEFAULT)
    tasks = ListField(ReferenceField(Task))
    endpoint = ReferenceField(Endpoint)

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
