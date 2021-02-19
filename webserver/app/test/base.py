import unittest
from app import app


class BaseTestCase(unittest.TestCase):
    """ Base Tests """

    def create_app(self):
        app.config.from_object('app.main.config.TestingConfig')
        return app

    def setUp(self):
        print(111)
        # app.config.db.create_all()
        # app.config.db.session.commit()

    def tearDown(self):
        print(222)
        # app.config.db.session.remove()
        # app.config.db.drop_all()

    @classmethod
    def tearDownClass(cls):
        print(444)

    @classmethod
    def setUpClass(cls):
        print(333)