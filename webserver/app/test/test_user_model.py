import unittest

import datetime

from app import app
from app.main.model.database import User
from app.test.base import BaseTestCase


class TestUserModel(BaseTestCase):

    def test_encode_auth_token(self):
        user = User(
            email='test@test.com',
            password='test',
            registered_on=datetime.datetime.utcnow()
        )
        app.config.db.session.add(user)
        app.config.db.session.commit()
        auth_token = User.encode_auth_token(user.pk)
        self.assertTrue(isinstance(auth_token, bytes))

    def test_decode_auth_token(self):
        user = User(
            email='test@test.com',
            password='test',
            registered_on=datetime.datetime.utcnow()
        )
        app.config.db.session.add(user)
        app.config.db.session.commit()
        auth_token = User.encode_auth_token(user.pk)
        self.assertTrue(isinstance(auth_token, bytes))
        self.assertTrue(User.decode_auth_token(auth_token.decode("utf-8") ) == 1)


if __name__ == '__main__':
    unittest.main()

