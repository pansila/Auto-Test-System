from mongoengine import *
from mongoengine.connection import disconnect

class Test(Document):
    schema_version = StringField(max_length=10, default='1')
    test_suite = StringField(max_length=100, unique=True, required=True)
    test_cases = ListField(StringField(max_length=100))
    parameters = DictField()
    path = StringField(max_length=300)
    author = StringField(max_length=50)
    create_date = DateTimeField()
    update_date = DateTimeField()

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
