import json
import os
from datetime import date, datetime, timedelta, timezone
from dateutil import parser
from pathlib import Path

from bson.objectid import ObjectId
from dateutil import tz
from flask import request, send_from_directory, url_for, current_app
from flask_restx import Resource
from mongoengine import DoesNotExist, ValidationError

from app.main.util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json
from app.main.util.get_path import get_test_results_root
from ..config import get_config
from ..model.database import *
from ..util.dto import TestResultDto
from ..util.response import *

api = TestResultDto.api
_test_report = TestResultDto.test_report
_record_test_result = TestResultDto.record_test_result
_test_result = TestResultDto.test_result

USERS_ROOT = Path(get_config().USERS_ROOT)


@api.route('/')
class TestResultRoot(Resource):
    @token_required
    @organization_team_required_by_args
    @api.doc('get_task_report_list')
    @api.param('page', description='The page number of the whole test report list')
    @api.param('limit', description='The item number of a page')
    @api.param('title', description='The test suite name')
    @api.param('priority', description='The priority of the task')
    @api.param('endpoint', description='The endpoint that runs the test')
    @api.param('sort', default='-run_date', description='The sort field')
    @api.param('start_date', description='The start date')
    @api.param('end_date', description='The end date')
    @api.marshal_list_with(_test_report)
    def get(self, **kwargs):
        """Get the task report list"""
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        priority = request.args.get('priority', default=None)
        endpoint_uid = request.args.get('endpoint', default=None)
        sort = request.args.get('sort', default='-run_date')
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        organization = kwargs['organization']
        team = kwargs['team']

        if start_date:
            start_date = parser.parse(start_date)
            if end_date is None:
                end_date = datetime.now(timezone.utc)
            else:
                end_date = parser.parse(end_date)

            if (start_date - end_date).days > 0:
                return response_message(EINVAL, 'start date {} is larger than end date {}'.format(start_date, end_date)), 401

            query = {'run_date__lte': end_date, 'run_date__gte': start_date, 'organization': organization}
        else:
            query = {'organization': organization}
        
        if team:
            query['team'] = team

        page = int(page)
        limit = int(limit)
        if page <= 0 or limit <= 0:
            return response_message(EINVAL, 'Field page and limit should be larger than 1'), 400

        if priority and priority != '' and priority.isdigit() and \
                int(priority) >= QUEUE_PRIORITY_MIN and int(priority) <= QUEUE_PRIORITY_MAX:
            query['priority'] = priority

        if title and priority != '':
            query['test_suite__contains'] = title

        if endpoint_uid and endpoint_uid != '':
            endpoint = Endpoint.objects(uid=endpoint_uid).first()
            if not endpoint:
                return response_message(EINVAL, 'Endpoint not found'), 400
            query['endpoint_run'] = endpoint

        try:
            dirs = os.listdir(get_test_results_root(team=team, organization=organization))
        except FileNotFoundError:
            return {'items': [], 'total': 0}
        ret = []
        for d in dirs:
            try:
                ObjectId(d)
            except ValidationError as e:
                current_app.logger.exception(e)
            else:
                ret.append(d)

        all_tasks = Task.objects(id__in=ret, **query).order_by(sort)
        ret = []
        for t in all_tasks[(page - 1) * limit : page * limit]:
            ret.append({
                'id': str(t.id),
                'test_suite': t.test_suite,
                'testcases': t.testcases,
                'comment': t.comment,
                'priority': t.priority,
                'run_date': t.run_date,
                'tester': t.tester.name,
                'status': t.status,
                'variables': t.variables,
                'endpoint_list': t.endpoint_list,
                'parallelization': t.parallelization
            })

        return {'items': ret, 'total': all_tasks.count()}

    # @token_required
    @api.doc('record_the_test_case')
    @api.expect(_record_test_result)
    def post(self):
        """create the test result in the database for a task"""
        data = request.json
        if data is None:
            return response_message(EINVAL, "Payload of the request is empty"), 400

        task_id = data.get('task_id', None)
        if task_id == None:
            return response_message(EINVAL, "Field task_id is required"), 400

        task = Task.objects(pk=task_id).first()
        if not task:
            return response_message(ENOENT, "Task not found"), 404

        test_case = data.get('test_case', None)
        if test_case == None:
            return response_message(EINVAL, "Field test_case is required"), 400

        test_result = TestResult()
        test_result.test_case = test_case
        test_result.task = task
        test_result.test_site = task.endpoint_run.name
        try:
            test_result.save()
        except ValidationError as e:
            current_app.logger.exception(e)
            return response_message(EINVAL, "Test result validation failed"), 400

        task.test_results.append(test_result)
        task.save()

@api.route('/<task_id>')
@api.param('task_id', 'id of the task for which to update the result')
class TestResultUpload(Resource):
    # @token_required
    @api.doc('update the test result')
    @api.expect(_test_result)
    def post(self, task_id):
        """
        Update the test result for the test case of a test suite

        Any items in the field more_result in the payload will be filled to the field more_result in the test result recorded in the database
        """
        data = request.json
        if data is None:
            return response_message(EINVAL, "Payload of the request is empty"), 400

        if isinstance(data, str):
            data = json.loads(data)

        task = Task.objects(pk=task_id).first()
        if not task:
            return response_message(ENOENT, "Task not found"), 404

        if not task.test_results:
            return response_message(ENOENT, "Test result not found"), 404

        cur_test_result = task.test_results[-1]

        for k, v in data.items():
            if k != 'more_result' and getattr(TestResult, k, None) != None:
                setattr(cur_test_result, k, v)
            else:
                cur_test_result.more_result[k] = v
        try:
            cur_test_result.save()
        except ValidationError as e:
            current_app.logger.exception(e)
            return response_message(EPERM, "Test result validation failed"), 400
