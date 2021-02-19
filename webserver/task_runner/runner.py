import asyncio
import aiofiles.os
import aiohttp_xmlrpc.client
import datetime
import json
import os
import pymongo
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from asyncio.exceptions import CancelledError
from io import StringIO
from pathlib import Path

import chardet
import websockets
from marshmallow.exceptions import ValidationError
from app import sio
from app.main.model.database import (EVENT_CODE_CANCEL_TASK,
                                     EVENT_CODE_START_TASK,
                                     EVENT_CODE_UPDATE_USER_SCRIPT,
                                     EVENT_CODE_GET_ENDPOINT_CONFIG,
                                     QUEUE_PRIORITY, Endpoint, EventQueue,
                                     Organization, Task, TaskQueue, Team)
from app.main.util import get_room_id, async_rmtree, async_exists, async_makedirs
from app.main.util.get_path import get_test_result_path, get_upload_files_root, get_user_scripts_root
from app.main.util.tarball import make_tarfile_from_dir

from bson import DBRef, ObjectId
from wsrpc import WebsocketRPC

from sanic import Blueprint
from sanic.log import logger
from sanic.websocket import ConnectionClosed, WebSocketProtocol

from task_runner.util.dbhelper import db_update_test
from task_runner.util.notification import notification_chain_call, notification_chain_init
from task_runner.util.xmlrpcserver import XMLRPCServer

ROBOT_PROCESSES = {}  # {task id: process instance}
TASK_PER_ENDPOINT = {}     # {taskqueue id: idle counter (int)}}
#TASK_LOCK = threading.Lock()
ROOM_MESSAGES = {}  # {"organziation:team": old_message, new_message}
RPC_PROXIES = {}    # {"endpoint_id": (websocket, rpc)}
TASKS_CACHED = {}

bp = Blueprint('rpc_proxy', url_prefix='/rpc_proxy')

async def event_handler_cancel_task(app, event):
    global ROBOT_PROCESSES, TASK_PER_ENDPOINT
    endpoint_uid = event.message['endpoint_uid']    # already uuid.UUID type
    priority = event.message['priority']
    task_id = event.message['task_id']
    organization = await event.organization.fetch()
    team = None
    if event.team:
        team = await event.team.fetch()

    task = await Task.find_one({'_id': ObjectId(task_id)})
    if not task:
        logger.error('Task not found for ' + task_id)
        return

    if endpoint_uid:
        endpoint = await Endpoint.find_one({'uid': endpoint_uid, 'organization': organization.pk, 'team': team.pk if team else None})
        if not endpoint:
            logger.error('Endpoint not found for {}'.format(endpoint_uid))
            return

        taskqueue = await TaskQueue.find_one({'organization': organization.pk, 'team': team.pk if team else None, 'endpoint': endpoint.pk, 'priority': priority})
        if not taskqueue:
            logger.error('Task queue not found for {}:{}'.format(endpoint_uid, priority))
            return
    else:
        taskqueue = await TaskQueue.find_one({'organization': organization.pk, 'team': team.pk if team else None, 'priority': priority, 'tasks': task.pk})
        if not taskqueue:
            logger.error('Task queue not found for task {}'.format(task_id))
            return
        taskqueue.tasks.remove(task)
        await taskqueue.commit()
        task.status = 'cancelled'
        await task.commit()
        logger.info('Waiting task cancelled')
        return

    if task.status == 'waiting':
        if taskqueue.running_task and taskqueue.running_task == task and str(endpoint.pk) in TASK_PER_ENDPOINT:
            logger.critical('Waiting task to run')
            for i in range(20):
                await task.reload()
                if task.status == 'running':
                    break
                await asyncio.sleep(0.1)
            else:
                logger.error('Waiting task to run timeouted out')
                del taskqueue.running_task
                await taskqueue.commit()
                task.status = 'cancelled'
                await task.commit()
        else:
            if taskqueue.running_task and taskqueue.running_task == task:
                del taskqueue.running_task
                await taskqueue.commit()
            taskqueue.tasks.remove(task)
            await taskqueue.commit()
            task.status = 'cancelled'
            await task.commit()
            logger.info('Waiting task cancelled without process running')
            return
    if task.status == 'running':
        if str(endpoint.pk) in TASK_PER_ENDPOINT:
            if str(task.pk) in ROBOT_PROCESSES:
                del taskqueue.running_task
                await taskqueue.commit()
                task.status = 'cancelled'
                await task.commit()

                ROBOT_PROCESSES[str(task.pk)].terminate()
                # del ROBOT_PROCESSES[task.pk]  # will be done in the task loop when robot process exits
                logger.info('Running task cancelled with process running')
                return
            else:
                logger.error('Task process not found when cancelling task (%s)' % task_id)
        del taskqueue.running_task
        await taskqueue.commit()
        task.status = 'cancelled'
        await task.commit()
        logger.info('Running task cancelled without process running')

async def event_handler_start_task(app, event):
    endpoint_uid = event.message['endpoint_uid']        # already uuid.UUID type
    to_delete = event.message['to_delete'] if 'to_delete' in event.message else False
    organization = await event.organization.fetch()
    team = await event.team.fetch() if event.team else None

    endpoint = await Endpoint.find_one({'organization': organization.pk, 'team': team.pk if team else None, 'uid': endpoint_uid})
    if not endpoint:
        org_name = (organization.name + '-' + team.name) if team else organization.name
        if not to_delete:
            logger.error('Endpoint not found for {}@{}'.format(org_name, endpoint_uid))
        return
    endpoint_id = str(endpoint.pk)

    def delete_task(task):
        del TASK_PER_ENDPOINT[endpoint_id]

    if endpoint_id not in TASK_PER_ENDPOINT:
        await reset_task_queue_status(app, organization, team)
        task = asyncio.create_task(process_task_per_endpoint(app, endpoint, organization, team))
        TASK_PER_ENDPOINT[endpoint_id] = 1
        task.add_done_callback(delete_task)
    else:
        TASK_PER_ENDPOINT[endpoint_id] = 2
        logger.info('Schedule the task to the pending queue')

async def event_handler_update_user_script(app, event):
    # TODO:
    return
    script = event.message['script']
    user = event.message['user']
    await db_update_test(script=script, user=user)

def event_handler_get_endpoint_config(app, event):
    uuid = event.message('uuid')
    fut = asyncio.run_coroutine_threadsafe(RPC_PROXIES[normalize_url(uuid)].request.run_keyword('get_endpoint_config', None, None), RPC_PROXIES['loop'])
    fut.result()

EVENT_HANDLERS = {
    EVENT_CODE_START_TASK: event_handler_start_task,
    EVENT_CODE_CANCEL_TASK: event_handler_cancel_task,
    EVENT_CODE_UPDATE_USER_SCRIPT: event_handler_update_user_script,
    EVENT_CODE_GET_ENDPOINT_CONFIG: event_handler_get_endpoint_config,
}

async def event_loop(app):
    eventqueue = await EventQueue.find_one()
    if not eventqueue:
        logger.error('event queue not found')
        return

    # async with EventQueue.collection.watch() as change_stream:
    #     async for change in change_stream:
    #         print(change)

    while True:
        try:
            event = await eventqueue.pop()
        except pymongo.errors.AutoReconnect:
            logger.warning('polling event queue network error')
            event = None
        if not event:
            await asyncio.sleep(1)
            continue

        if isinstance(event, DBRef):
            logger.warning('event {} has been deleted, ignore it'.format(event.pk))
            continue

        logger.info('Start to process event {} ...'.format(event.code))

        try:
            await EVENT_HANDLERS[event.code](app, event)
            event.status = 'Processed'
            await event.commit()
        except KeyError:
            logger.error('Unknown message: %s' % event.code)

def convert_json_to_robot_variable(variables, default_variables, variable_file):
    sub_type = 0
    sub_vars = []
    p = re.compile(r'\${(.*?)}')

    def is_number(s):
        try:
            float(s)
            return True
        except ValueError:
            pass
        try:
            int(s, 16)
            return True
        except ValueError:
            pass
        try:
            int(s, 8)
            return True
        except ValueError:
            pass
        try:
            int(s, 2)
            return True
        except ValueError:
            pass
        return False

    def var_replace(m):
        nonlocal sub_type
        val = m.group(1)
        sub_type = 1
        if val.upper() == 'TRUE':
            return 'True'
        elif val.upper() == 'FALSE':
            return 'False'
        elif val.upper() == 'NULL':
            return 'None'
        elif val.upper() == 'EMPTY':
            return '\'\''
        elif val.upper() == 'SPACE':
            return '\' \''
        elif is_number(val):
            return val
        else:
            sub_type = 2
            sub_vars.append(val.replace(' ', '_'))
            return '{' + val.replace(' ', '_') + '}'

    def sub_variable(v, key=None):
        nonlocal sub_type
        sub_type = 0
        subVal = p.sub(var_replace, v)
        if sub_type == 2:
            if key:
                return f'\'{key}\': f\'{subVal}\''
            else:
                return f'f\'{subVal}\''
        elif sub_type == 1:
            if key:
                return f'\'{key}\': {subVal}'
            else:
                return f'{subVal}'
        else:
            if key:
                return f'\'{key}\': \'{subVal}\''
            else:
                return f'\'{subVal}\''

    with open(variable_file, 'w') as f:
        t = StringIO()
        for k, v in variables.items():
            if isinstance(v, str):
                t.write(k + ' = ')
                t.write(sub_variable(v))
                t.write('\n')
            elif isinstance(v, list):
                t.write(k + ' = [')
                t.write(', '.join(sub_variable(vv) for vv in v if isinstance(vv, str)))
                t.write(']\n')
            elif isinstance(v, dict):
                t.write(k + ' = {')
                t.write(', '.join(sub_variable(v[kk], kk) for kk in v if isinstance(v[kk], str)))
                t.write('}\n')
        ref_vars = [(k, default_variables[k]) for k in default_variables if k in sub_vars]
        for k, v in ref_vars:
            f.write(f'{k} = \'{v}\'\n')
        f.write(t.getvalue())


async def process_task_per_endpoint(app, endpoint, organization=None, team=None):
    global ROBOT_PROCESSES, TASKS_CACHED

    if not organization and not team:
        logger.error('Argument organization and team must neither be None')
        return
    room_id = get_room_id(str(organization.pk), str(team.pk) if team else '')

    taskqueues = await TaskQueue.find({'organization': organization.pk, 'team': team.pk if team else None, 'endpoint': endpoint.pk}).to_list(len(QUEUE_PRIORITY))
    if len(taskqueues) == 0:
        logger.error('Taskqueue not found')
        return
    # taskqueues = [q for q in taskqueues]  # query becomes stale if the document it points to gets changed elsewhere, use document instead of query to perform deletion
    taskqueue_first = taskqueues[0]

    endpoint_id = str(endpoint.pk)
    endpoint_uid = endpoint.uid
    if team and not organization:
        organization = await team.organization.fetch()
    org_name = (organization.name + '-' + team.name) if team else organization.name

    while True:
        await taskqueue_first.reload()
        if taskqueue_first.to_delete:
            for taskqueue in taskqueues:
                await taskqueue.delete()
            await endpoint.delete()
            logger.info('Abort the task loop: {} @ {}'.format(org_name, endpoint_uid))
            break
        # TODO: lower priority tasks will take precedence if higher priority queue is empty first
        # but filled then when thread is searching for tasks in the lower priority task queues
        for priority in QUEUE_PRIORITY:
            exit_task = False
            for taskqueue in taskqueues:
                await taskqueue.reload()
                if taskqueue.to_delete:
                    exit_task = True
                    break
                if taskqueue.priority == priority:
                    break
            else:
                logger.error('Found task queue with unknown priority')
                continue

            if exit_task:
                break

            # "continue" to search for tasks in the lower priority task queues
            # "break" to start over to search for tasks from the top priority task queue
            task = await taskqueue.pop()
            if not task:
                continue
            task_id = str(task.pk)
            if isinstance(task, DBRef):
                logger.warning('task {} has been deleted, ignore it'.format(task_id))
                taskqueue.running_task = None
                await taskqueue.commit()
                break

            if task.kickedoff != 0 and not task.parallelization:
                logger.info('task has been taken over by other threads, do nothing')
                taskqueue.running_task = None
                await taskqueue.commit()
                break

            await task.collection.find_one_and_update({'_id': task.pk}, {'$inc': {'kickedoff': 1}})
            await task.reload()
            if task.kickedoff != 1 and not task.parallelization:
                logger.warning('a race condition happened')
                taskqueue.running_task = None
                await taskqueue.commit()
                break
            test = await task.test.fetch()

            logger.info('Start to run task {} in the thread {}'.format(task_id, threading.current_thread().name))

            result_dir = await get_test_result_path(task)
            scripts_dir = await get_user_scripts_root(task)
            await async_makedirs(result_dir)

            args = ['--loglevel', 'debug', '--outputdir', str(result_dir),
                    '--consolecolors', 'on', '--consolemarkers', 'on']

            if hasattr(task, 'testcases'):
                for t in task.testcases:
                    args.extend(['-t', t])

            if hasattr(task, 'variables') and task.variables:
                variable_file = result_dir / 'variablefile.py'
                convert_json_to_robot_variable(task.variables, test.variables, variable_file)
                args.extend(['--variablefile', str(variable_file)])

            addr, port = '127.0.0.1', 8270
            args.extend(['-v', f'address_daemon:{addr}', '-v', f'port_daemon:{port}',
                        '-v', f'task_id:{task_id}', '-v', f'endpoint_uid:{endpoint_uid}'])
            args.append(os.path.join(scripts_dir, test.path, test.test_suite + '.md'))
            logger.info('Arguments: ' + str(args))

            p = await asyncio.create_subprocess_exec('robot', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            ROBOT_PROCESSES[str(task.pk)] = p

            task.status = 'running'
            task.run_date = datetime.datetime.utcnow()
            task.endpoint_run = endpoint
            await task.commit()
            await sio.emit('task started', {'task_id': task_id}, room=room_id)

            log_msg = StringIO()
            if room_id not in ROOM_MESSAGES:
                ROOM_MESSAGES[room_id] = {task_id: log_msg}
            else:
                if task_id not in ROOM_MESSAGES[room_id]:
                    ROOM_MESSAGES[room_id][task_id] = log_msg
            ss = b''
            msg_q = asyncio.Queue()
            async def _read_log():
                nonlocal msg_q, ss, log_msg
                while True:
                    c = await p.stdout.read(1)
                    if not c:
                        await msg_q.put(None)
                        break
                    try:
                        c = c.decode()
                    except UnicodeDecodeError:
                        ss += c
                    else:
                        c = '\r\n' if c == '\n' else c
                        log_msg.write(c)
                        await msg_q.put(c)
            asyncio.create_task(_read_log())

            async def _emit_log():
                nonlocal msg_q
                msg = ''
                while True:
                    try:
                        c = msg_q.get_nowait()
                    except asyncio.QueueEmpty:
                        if msg:
                            await sio.emit('test report', {'task_id': task_id, 'message': msg}, room=room_id)
                            msg = ''
                        c = await msg_q.get()
                    finally:
                        if c:
                            msg += c
                        else:
                            break
            emit_log_task = asyncio.create_task(_emit_log())
            await emit_log_task

            del ROBOT_PROCESSES[str(task.pk)]

            if ss != b'':
                log_msg_all = StringIO()
                log_msg_all.write(log_msg.getvalue())
                try:
                    ss = ss.decode(chardet.detect(ss)['encoding'])
                except UnicodeDecodeError:
                    try:
                        logger.warning(f'chardet error: {ss.decode("unicode_escape").encode("latin-1")}')
                    except UnicodeEncodeError:
                        pass
                else:
                    log_msg_all.write(ss)
                logger.info('\n' + log_msg_all.getvalue())
                await sio.emit('test report', {'task_id': task_id, 'message': ss}, room=room_id)
            else:
                logger.info('\n' + log_msg.getvalue())

            await p.wait()
            if p.returncode == 0:
                task.status = 'successful'
            else:
                await task.reload()
                if task.status != 'cancelled':
                    task.status = 'failed'
            await task.commit()
            await sio.emit('task finished', {'task_id': task_id, 'status': task.status}, room=room_id)
            ROOM_MESSAGES[room_id][task_id].close()
            del ROOM_MESSAGES[room_id][task_id]
            if task_id in TASKS_CACHED:
                del TASKS_CACHED[task_id]

            del taskqueue.running_task
            await taskqueue.commit()
            endpoint.last_run_date = datetime.datetime.utcnow()
            await endpoint.commit()

            if task.upload_dir:
                resource_dir_tmp = get_upload_files_root(task)
                if await async_exists(resource_dir_tmp):
                    await make_tarfile_from_dir(str(result_dir / 'resource.tar.gz'), resource_dir_tmp)

            result_dir_tmp = result_dir / 'temp'
            if await async_exists(result_dir_tmp):
                await async_rmtree(result_dir_tmp)

            await notification_chain_call(task)
            TASK_PER_ENDPOINT[endpoint_id] = 1
            break
        else:
            if TASK_PER_ENDPOINT[endpoint_id] != 1:
                TASK_PER_ENDPOINT[endpoint_id] = 1
                logger.info('Run the recently scheduled task')
                continue
            # del TASK_PER_ENDPOINT[endpoint_id]
            logger.info('task processing finished, exiting the process loop')
            break

async def check_endpoint(app, endpoint_uid, organization, team):
    if team:
        assert organization == team.organization
    org_name = (organization.name + '-' + team.name) if team else organization.name
    url = 'http://127.0.0.1:8270/{}'.format(endpoint_uid)
    server = aiohttp_xmlrpc.client.ServerProxy(url)
    endpoint = await Endpoint.find_one({'uid': endpoint_uid, 'organization': organization.pk, 'team': team.pk if team else None})
    try:
        ret = await server.get_keyword_names()
    except ConnectionRefusedError:
        err_msg = 'Endpoint {} @ {} connecting failed'.format(endpoint.name, org_name)
    except asyncio.exceptions.TimeoutError:
        err_msg = 'Endpoint {} @ {} connecting timeouted'.format(endpoint.name, org_name)
    # except xmlrpc.client.Fault as e:  # TODO
    #     err_msg = 'Endpoint {} @ {} RPC calling error'.format(endpoint.name, org_name)
    #     logger.exception(e)
    except OSError as e:
        err_msg = 'Endpoint {} @ {} unreachable'.format(endpoint.name, org_name)
    except Exception as e:
        err_msg = 'Endpoint {} @ {} has error:'.format(endpoint.name, org_name)
        logger.exception(e)
    else:
        if ret:
            if endpoint and endpoint.status == 'Offline':
                endpoint.status = 'Online'
                await endpoint.commit()
            await server.close()
            return True
        else:
            err_msg = 'Endpoint {} @ {} RPC proxy not found'.format(endpoint.name, org_name)
    if endpoint and endpoint.status == 'Online':
        logger.error(err_msg)
        endpoint.status = 'Offline'
        await endpoint.commit()
    await server.close()
    return False

def normalize_url(url):
    if not url.startswith('/'):
        url = '/' + url
    if url.endswith('/'):
        url = url[:-1]
    return url

@bp.websocket('/msg')
async def rpc_message_relay(request, ws):
    global TASKS_CACHED
    while True:
        try:
            ret = await ws.recv()
            ret = json.loads(ret)
        except Exception as e:
            pass
        if 'task_id' not in ret:
            return
        task_id = ret['task_id']
        if not task_id:
            # task daemon's message
            continue
        data = ret['data']
        if task_id not in TASKS_CACHED:
            task = await Task.find_one({'_id': ObjectId(task_id)})
            TASKS_CACHED[task_id] = task
        else:
            task = TASKS_CACHED[task_id]
        room_id = get_room_id(str(task.organization.id), str(task.team.id) if task.team else '')
        await sio.emit('test log', {'task_id': task_id, 'message': data}, room=room_id)

@bp.websocket('/rpc')
async def rpc_proxy(request, ws):
    # need to protect from DDos attacking
    global RPC_PROXIES
    RPC_PROXIES['loop'] = asyncio.get_event_loop()

    ret = await ws.recv()
    try:
        data = json.loads(ret)
    except Exception as e:
        print(f'Received an unknown format json data: {e}')
        return
    join_id = data['join_id']
    uid = data['uid']
    backing_file = data['backing_file']
    organization, team = None, None

    endpoint = await Endpoint.find_one({'uid': uuid.UUID(uid)})
    if endpoint and endpoint.status == 'Forbidden':
        await ws.send(endpoint.status)
        return
    organization = await Organization.find_one({'_id': ObjectId(join_id)})
    team = await Team.find_one({'_id': ObjectId(join_id)})
    if not organization:
        if not team:
            await ws.send('Organization or team not found')
            return
        organization = await team.organization.fetch()
    if not endpoint:
        try:
            endpoint = Endpoint(uid=uid, organization=organization, status='Unauthorized')
            if team:
                endpoint.team = team
            await endpoint.commit()
        except ValidationError:
            print('Endpoint uid %s validation error' % uid)
            return
        print('Received a new endpoint with uid %s' % uid)
        return
    if endpoint.organization != organization or endpoint.team != team:
        endpoint.organization = organization
        endpoint.team = team
        endpoint.status = 'Unauthorized'
        await endpoint.commit()
    if endpoint.status == 'Unauthorized':
        await ws.send(endpoint.status)
        return
    await ws.send('OK')

    def error_check(fut):
        try:
            fut.result()
        except websockets.exceptions.ConnectionClosedError as error:
            if len(rpc._request_table.keys()) != 0:
                print(f'Endpoint {endpoint.name}@{url} was aborted, flushing pending tasks...')
                for k in rpc._request_table:
                    rpc._request_table[k].set_result({'status': 'FAIL', 'error': str(error)})
                rpc._request_table = {}
        except CancelledError:
            pass

    rpc = WebsocketRPC(ws, client_mode=True)
    rpc.client_task.add_done_callback(error_check)
    url = normalize_url(uid + '/' + backing_file)
    if url in RPC_PROXIES:
        await RPC_PROXIES[url].close()
        del RPC_PROXIES[url]
    RPC_PROXIES[url] = rpc
    print(f'Received an endpoint {endpoint.name}@{url} connecting to {organization.name }@{team and team.name or ""}')

    try:
        await ws.wait_closed()
    except (CancelledError, ConnectionClosed):
        print(f'Endpoint {endpoint.name}@{url} disconnected')

    if len(rpc._request_table.keys()) != 0:
        print(f'Endpoint {endpoint.name}@{url} was closed, flushing pending tasks...')
        for k in rpc._request_table:
            rpc._request_table[k].set_result({'status': 'FAIL', 'error': f'Connection of {url} was lost, possibly due to long time blocking operations'})
        rpc._request_table = {}

    try:
        await RPC_PROXIES[url].close()
    except websockets.exceptions.ConnectionClosedError:
        pass
        # print(f'websocket close error for endpoint {url}')
    del RPC_PROXIES[url]

def restart_interrupted_tasks(app, organization=None, team=None):
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

async def reset_event_queue_status(app):
    queue = await EventQueue.find_one()
    if not queue:
        await EventQueue().commit()
        queue = await EventQueue.find_one()
        logger.warning('Event queue has not been created')

    ret = await queue.collection.find_one_and_update({'_id': queue.pk, 'rw_lock': True}, {'$set': {'rw_lock': False}})
    if ret:
        logger.info('Reset the read/write lock for event queue')

async def reset_task_queue_status(app, organization=None, team=None):
    cnt = 0
    async for q in TaskQueue.find({'organization': organization.pk, 'team': team.pk if team else None}):
        ret = await q.collection.find_one_and_update({'_id': q.pk, 'rw_lock': True}, {'$set': {'rw_lock': False}})
        if ret:
            logger.info('Reset the read/write lock for queue {} with priority {}'.format(q.endpoint.uid, q.priority))
        cnt += 1
    if cnt == 0:
        logger.error('Task queue has not been created')
        return 1

    return 0

async def prepare_to_run(app, organization=None, team=None):
    ret = await reset_event_queue_status(app)
    if ret:
        return ret

    ret = await reset_task_queue_status(app, organization, team)
    if ret:
        return ret

    ret = await restart_interrupted_tasks(app, organization, team)
    if ret:
        return ret

    return 0

async def start_event_thread(app):
    logger.info('Start the event loop')
    await reset_event_queue_status(app)
    await event_loop(app)

async def start_heartbeat_thread(app):
    logger.info('Start the endpoint online check loop')
    while True:
        async for endpoint in Endpoint.find():
            organization = await endpoint.organization.fetch()
            team = None
            if endpoint.team:
                team = await endpoint.team.fetch()
            await check_endpoint(app, endpoint.uid, organization, team)
        await asyncio.sleep(30)

def start_xmlrpc_server(app):
    logger.info('Start local XML RPC server')
    thread = XMLRPCServer(RPC_PROXIES, host='0.0.0.0', port=8270)
    thread.daemon = True
    thread.start()

def initialize_runner(app):
    notification_chain_init(app)

if __name__ == '__main__':
    pass
