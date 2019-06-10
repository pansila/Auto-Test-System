import json
import os
from datetime import date, datetime, timedelta, timezone
from dateutil import parser
from pathlib import Path

from bson.objectid import ObjectId
from dateutil import tz
from flask import Flask, render_template, request, send_from_directory, url_for
from flask_restplus import Resource
from mongoengine import DoesNotExist, ValidationError

from app.main.util.decorator import token_required
from app.main.util.request_parse import parse_organization_team
from ..config import get_config
from ..model.database import *
from ..util.dto import TestResultDto
from ..util.errors import *

api = TestResultDto.api

USERS_ROOT = Path(get_config().USERS_ROOT)


@api.route('/')
class TestResultRoot(Resource):
    @token_required
    def get(self, user):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        priority = request.args.get('priority', default=None)
        endpoint = request.args.get('endpoint', default=None)
        sort = request.args.get('sort', default='-run_date')
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        ret = parse_organization_team(user, request.args)
        if len(ret) != 3:
            return ret
        owner, team, organization = ret

        if start_date:
            start_date = parser.parse(start_date)
            if end_date is None:
                end_date = datetime.now(timezone.utc)
            else:
                end_date = parser.parse(end_date)

            if (start_date - end_date).days > 0:
                return error_message(EINVAL, 'start date {} is larger than end date {}'.format(start_date, end_date)), 401

            query = {'run_date__lte': end_date, 'run_date__gte': start_date, 'organization': organization}
        else:
            query = {'organization': organization}
        
        if team:
            query['team'] = team

        page = int(page)
        limit = int(limit)

        if priority and priority != '' and priority.isdigit() and \
                int(priority) >= QUEUE_PRIORITY_MIN and int(priority) <= QUEUE_PRIORITY_MAX:
            query['priority'] = priority

        if title and priority != '':
            query['test_suite__contains'] = title

        if endpoint and endpoint != '':
            query['endpoint_run'] = endpoint

        try:
            dirs = os.listdir(USERS_ROOT / organization.path / 'test_results')
        except FileNotFoundError:
            return {'items': [], 'total': 0}

        all_tasks = Task.objects(id__in=dirs, **query).order_by(sort)
        tasks = all_tasks[(page - 1) * limit : page * limit]
        ret = []
        for t in tasks:
            ret.append({
                'id': str(t.id),
                'test_suite': t.test_suite,
                'testcases': t.testcases,
                'comment': t.comment,
                'priority': t.priority,
                'run_date': t.run_date.timestamp() * 1000,
                'tester': t.tester.name,
                'status': t.status
            })

        return {'items': ret, 'total': all_tasks.count()}

@api.route('/')
class TestResultCreate(Resource):
    # @token_required
    @api.doc('create the test result for the task in the database')
    def post(self):
        data = request.json
        if data is None:
            return error_message(EINVAL, "Payload of the request is empty"), 400

        task_id = data.get('task_id', None)
        if task_id == None:
            return error_message(EINVAL, "Field task_id is required"), 400
        try:
            task = Task.objects(pk=task_id).get()
        except Task.DoesNotExist as e:
            print(e)
            return error_message(ENOENT, "Task not found"), 404

        test_case = data.get('test_case', None)
        if test_case == None:
            return error_message(EINVAL, "Field test_case is required"), 400

        test_result = TestResult()
        test_result.test_case = test_case
        test_result.task = task
        try:
            test_result.save()
        except ValidationError as e:
            print(e)
            return error_message(EINVAL, "Test result validation failed"), 400

        task.test_results.append(test_result)
        task.save()

@api.route('/<task_id>')
@api.param('task_id', 'id of the task for which to upload the results')
class TestResultUpload(Resource):
    # @token_required
    @api.doc('update the test results')
    def post(self, task_id):
        data = request.json
        if data is None:
            return error_message(EINVAL, "Payload of the request is empty"), 400

        if isinstance(data, str):
            data = json.loads(data)

        task = Task.objects(pk=task_id).first()
        if not task:
            return error_message(ENOENT, "Task not found"), 404

        if not task.test_results:
            return error_message(ENOENT, "Test result not found"), 404

        cur_test_result = task.test_results[-1]

        for k, v in data.items():
            if k != 'more_result' and getattr(TestResult, k, None) != None:
                setattr(cur_test_result, k, v)
            else:
                cur_test_result.more_result[k] = v
        try:
            cur_test_result.save()
        except ValidationError as e:
            print(e)
            return error_message(EPERM, "Test result validation failed"), 400
