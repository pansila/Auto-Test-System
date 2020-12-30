import json as py_json
import os
import uuid
import pymongo

from datetime import date, datetime, timedelta, timezone
from dateutil import parser, tz
from pathlib import Path
from bson.objectid import ObjectId
from marshmallow.exceptions import ValidationError

from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file, html
from sanic_openapi import doc

from ..util import async_listdir
from ..util.decorator import token_required, organization_team_required_by_args, organization_team_required_by_json
from ..util.get_path import get_test_results_root
from ..config import get_config
from ..model.database import QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_MIN, Endpoint, Task, TestResult
from ..util.dto import TestResultDto, json_response
from ..util.response import response_message, ENOENT, EINVAL, SUCCESS, EPERM

_test_report = TestResultDto.test_report
_record_test_result = TestResultDto.record_test_result
_test_result_query = TestResultDto.test_result_query
_test_result = TestResultDto.test_result

USERS_ROOT = Path(get_config().USERS_ROOT)

bp = Blueprint('testresult', url_prefix='/testresult')

class TestResultView(HTTPMethodView):
    @doc.summary('get the task report list')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_test_result_query)
    @doc.produces(_test_report)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        page = request.args.get('page', default=1)
        limit = request.args.get('limit', default=10)
        title = request.args.get('title', default=None)
        priority = request.args.get('priority', default=None)
        endpoint_uid = request.args.get('endpoint', default=None)
        sort = request.args.get('sort', default='-run_date')
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)

        organization = request.ctx.organization
        team = request.ctx.team

        if start_date:
            start_date = parser.parse(start_date)
            if end_date is None:
                end_date = datetime.now(timezone.utc)
            else:
                end_date = parser.parse(end_date)

            if (start_date - end_date).days > 0:
                return json(response_message(EINVAL, 'start date {} is larger than end date {}'.format(start_date, end_date)))

            query = {'run_date': {'$lte': end_date, '$gte': start_date}, 'organization': organization.pk}
        else:
            query = {'organization': organization.pk}
        
        if team:
            query['team'] = team.pk

        page = int(page)
        limit = int(limit)
        if page <= 0 or limit <= 0:
            return json(response_message(EINVAL, 'Field page and limit should be larger than 1'))

        if priority and priority != '' and priority.isdigit() and \
                int(priority) >= QUEUE_PRIORITY_MIN and int(priority) <= QUEUE_PRIORITY_MAX:
            query['priority'] = priority

        if title and priority != '':
            query['test_suite'] = {'$regex': title}

        if endpoint_uid and endpoint_uid != '':
            endpoint = await Endpoint.find_one({'uid': uuid.UUID(endpoint_uid)})
            if not endpoint:
                return json(response_message(EINVAL, 'Endpoint not found'))
            query['endpoint_run'] = endpoint.pk

        try:
            dirs = await async_listdir(await get_test_results_root(team=team, organization=organization))
        except FileNotFoundError:
            return json(response_message(ENOENT, 'test result files not found', items=[], total=0))
        ret = []
        for d in dirs:
            try:
                ObjectId(d)
            except ValidationError as e:
                logger.exception(e)
            else:
                ret.append(d)

        query['id'] = {'$in': ret}
        ret = []

        sort_string_start = 1 if sort[0] in ('-', '+') else 0
        async for t in Task.find(query).sort(sort[sort_string_start:], pymongo.DESCENDING if sort[0] == '-' else pymongo.ASCENDING).skip((page - 1) * limit).limit(limit):
            tester = await t.tester.fetch()
            test = await t.test.fetch() 
            test_id = str(test.pk) if test else None
            ret.append({
                'id': str(t.pk),
                'test_id': test_id,
                'test_suite': t.test_suite,
                'testcases': t.testcases,
                'comment': t.comment,
                'priority': t.priority,
                'run_date': t.run_date.timestamp() * 1000,
                'tester': tester.name,
                'status': t.status,
                'variables': t.variables,
                'endpoint_list': t.endpoint_list,
                'parallelization': t.parallelization
            })

        return json(response_message(SUCCESS, test_reports=ret, total=(await Task.count_documents(query))))

    @doc.summary('create the test result in the database for a task')
    @doc.consumes(_record_test_result, location='body')
    @doc.produces(json_response)
    # @token_required #TODO
    async def post(self, request):
        data = request.json

        task_id = data.get('task_id', None)
        if not task_id:
            return json(response_message(EINVAL, "Field task_id is required"))

        task = await Task.find_one({'_id': ObjectId(task_id)})
        if not task:
            return json(response_message(ENOENT, "Task not found"))

        test_case = data.get('test_case', None)
        if test_case == None:
            return json(response_message(EINVAL, "Field test_case is required"))

        endpoint = await task.endpoint_run.fetch()
        try:
            test_result = TestResult()
            test_result.test_case = test_case
            test_result.task = task
            test_result.test_site = endpoint.name
        except ValidationError as e:
            logger.exception(e)
            return json(response_message(EINVAL, "Test result validation failed"))

        await test_result.commit()

        if not task.test_results:
            task.test_results = [test_result]
        else:
            task.test_results.append(test_result)
        await task.commit()

        return json(response_message(SUCCESS))

@bp.post('/<task_id>')
@doc.summary('Update the test result for the test case of a test suite')
@doc.description('Any items in the field more_result in the payload will be filled to the field more_result in the test result recorded in the database')
@doc.consumes(_test_result, location='body')
@doc.produces(json_response)
# @token_required #TODO
async def handler(request, task_id):
    data = request.json
    if data is None:
        return json(response_message(EINVAL, "Payload of the request is empty"))

    if isinstance(data, str):
        data = py_json.loads(data)

    task = await Task.find_one({'_id': ObjectId(task_id)})
    if not task:
        return json(response_message(ENOENT, "Task not found"))

    if not task.test_results:
        return json(response_message(ENOENT, "The tasks's test result has not been created"))

    cur_test_result = await task.test_results[-1].fetch()
    if not cur_test_result:
        return json(response_message(ENOENT, "Test result not found"))

    for k, v in data.items():
        if k != 'more_result' and getattr(TestResult, k, None) != None:
            cur_test_result[k] = v
        else:
            if not cur_test_result.more_result:
                cur_test_result.more_result = {}
            cur_test_result.more_result[k] = v

    await cur_test_result.commit()

    return json(response_message(SUCCESS))

bp.add_route(TestResultView.as_view(), '/')
