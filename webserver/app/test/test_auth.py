import unittest

import json
import time
from app import app
from app.test.base import BaseTestCase
from app.main.util.response import USER_NOT_EXIST


def register_user(self):
    request, response = app.test_client.post(
        '/api_v1/user/',
        json=dict(
            email='joe@gmail.com',
            username='username',
            password='123456'
        )
    )
    return response


def login_user(self):
    request, response = app.test_client.post(
        '/api_v1/auth/login',
        json=dict(
            email='joe@gmail.com',
            password='123456'
        )
    )
    return response


class TestAuthBlueprint(BaseTestCase):
    def test_registration(self):
        """ Test for user registration """
        response = register_user(self)
        self.assertTrue(response.json['status'] == 'success')
        self.assertTrue(response.json['message'] == 'Successfully registered.')
        self.assertTrue(response.json['Authorization'])
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 201)

    def test_registered_with_already_registered_user(self):
        """ Test registration with already registered email"""
        register_user(self)
        response = register_user(self)
        self.assertTrue(response.json['status'] == 'fail')
        self.assertTrue(
            response.json['message'] == 'User already exists. Please Log in.')
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 409)

    def test_registered_user_login(self):
        """ Test for login of registered-user login """
        # user registration
        resp_register = register_user(self)
        self.assertTrue(resp_register.json['status'] == 'success')
        self.assertTrue(
            resp_register.json['message'] == 'Successfully registered.'
        )
        self.assertTrue(resp_register.json['Authorization'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # registered user login
        response = login_user(self)
        self.assertTrue(response.json['status'] == 'success')
        self.assertTrue(response.json['message'] == 'Successfully logged in.')
        self.assertTrue(response.json['Authorization'])
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 200)

    def test_non_registered_user_login(self):
        """ Test for login of non-registered user """
        response = login_user(self)
        self.assertTrue(response.json['code'] == USER_NOT_EXIST.code)
        print(response.json['message'])
        self.assertTrue(response.json['message'] == USER_NOT_EXIST.message)
        self.assertTrue(response.content_type == 'application/json')
        self.assertEqual(response.status_code, 200)

    def test_valid_logout(self):
        """ Test for logout before token expires """
        # user registration
        resp_register = register_user(self)
        data_register = json.loads(resp_register.data.decode())
        self.assertTrue(data_register['status'] == 'success')
        self.assertTrue(
            data_register['message'] == 'Successfully registered.')
        self.assertTrue(data_register['Authorization'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # user login
        resp_login = login_user(self)
        data_login = json.loads(resp_login.data.decode())
        self.assertTrue(data_login['status'] == 'success')
        self.assertTrue(data_login['message'] == 'Successfully logged in.')
        self.assertTrue(data_login['Authorization'])
        self.assertTrue(resp_login.content_type == 'application/json')
        self.assertEqual(resp_login.status_code, 200)
        # valid token logout
        response = self.client.post(
            '/auth/logout',
            headers=dict(
                Authorization='Bearer ' + json.loads(
                    resp_login.data.decode()
                )['Authorization']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'success')
        self.assertTrue(data['message'] == 'Successfully logged out.')
        self.assertEqual(response.status_code, 200)

    def test_valid_blacklisted_token_logout(self):
        """ Test for logout after a valid token gets blacklisted """
        from app.main.model.database import BlacklistToken
        # user registration
        resp_register = register_user(self)
        data_register = json.loads(resp_register.data.decode())
        self.assertTrue(data_register['status'] == 'success')
        self.assertTrue(
            data_register['message'] == 'Successfully registered.')
        self.assertTrue(data_register['Authorization'])
        self.assertTrue(resp_register.content_type == 'application/json')
        self.assertEqual(resp_register.status_code, 201)
        # user login
        resp_login = login_user(self)
        data_login = json.loads(resp_login.data.decode())
        self.assertTrue(data_login['status'] == 'success')
        self.assertTrue(data_login['message'] == 'Successfully logged in.')
        self.assertTrue(data_login['Authorization'])
        self.assertTrue(resp_login.content_type == 'application/json')
        self.assertEqual(resp_login.status_code, 200)
        # blacklist a valid token
        blacklist_token = BlacklistToken(
            token=json.loads(resp_login.data.decode())['Authorization'])
        app.config.db.session.add(blacklist_token)
        app.config.db.session.commit()
        # blacklisted valid token logout
        response = self.client.post(
            '/auth/logout',
            headers=dict(
                Authorization='Bearer ' + json.loads(
                    resp_login.data.decode()
                )['Authorization']
            )
        )
        data = json.loads(response.data.decode())
        self.assertTrue(data['status'] == 'fail')
        self.assertTrue(data['message'] == 'Token blacklisted. Please log in again.')
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
