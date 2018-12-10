from mongoengine import *

class TestResult(Document):
    schema_version = StringField(max_length=10, default='1')
    test_case = StringField(max_length=100, required=True)
    test_site = StringField(max_length=50)
    tester = StringField(max_length=20)
    tester_email = EmailField()
    test_date = DateTimeField()
    test_report = StringField(max_length=200)
    status = StringField(max_length=10)
    duration = IntField()

    meta = {'allow_inheritance': True}

class MongoDBClient():

    def __init__(self, config):
        connect('autotest', host=self.config['mongodb_uri'], port=self.config['mongodb_port'])
