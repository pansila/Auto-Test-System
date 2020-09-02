import argparse
import asyncio
import chardet
import datetime
import functools
import json
import os
import pymongo
import queue
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import xmlrpc.client
from io import StringIO
from pathlib import Path

import eventlet
import mongoengine
import websockets
from mongoengine import ValidationError
from app.main.config import get_config
from app.main.model.database import Endpoint, Task, TaskQueue, EventQueue, Organization, Team, \
        EVENT_CODE_CANCEL_TASK, EVENT_CODE_START_TASK, EVENT_CODE_UPDATE_USER_SCRIPT, QUEUE_PRIORITY
from app.main.util import get_room_id
from app.main.util.get_path import get_test_result_path, get_upload_files_root, get_user_scripts_root
from app.main.util.tarball import make_tarfile_from_dir
from bson import DBRef, ObjectId
from mongoengine import connect
from sanic import Sanic
from sanic.websocket import WebSocketProtocol
from task_runner.util.dbhelper import db_update_test
from task_runner.util.notification import (notification_chain_call,
                                           notification_chain_init)
from task_runner.util.xmlrpcserver import XMLRPCServer
from wsrpc import WebsocketRPC, RemoteCallError
from asyncio.exceptions import CancelledError
from sanic.websocket import ConnectionClosed

ROBOT_PROCESSES = {}  # {task id: process instance}
TASK_THREADS = {}     # {taskqueue id: idle counter (int)}}
TASK_LOCK = threading.Lock()
ROOM_MESSAGES = {}  # {"organziation:team": old_message, new_message}
RPC_PROXIES = {}    # {"endpoint_id": (websocket, rpc)}
RPC_SOCKET = None
TASKS_CACHED = {}

RPC_APP = Sanic('RPC Proxy app')

def install_sio(sio):
    global RPC_SOCKET
    RPC_SOCKET = sio

def event_handler_cancel_task(app, event):
    global ROBOT_PROCESSES, TASK_THREADS
    endpoint_uid = event.message['endpoint_uid']
    priority = event.message['priority']
    task_id = event.message['task_id']

    task = Task.objects(pk=task_id).first()
    if not task:
        app.logger.error('Task not found for ' + task_id)
        return

    if endpoint_uid:
        endpoint = Endpoint.objects(uid=endpoint_uid, organization=event.organization, team=event.team).first()
        if not endpoint:
            app.logger.error('Endpoint not found for {}'.format(endpoint_uid))
            return

        taskqueue = TaskQueue.objects(organization=event.organization, team=event.team, endpoint=endpoint, priority=priority).first()
        if not taskqueue:
            app.logger.error('Task queue not found for {}:{}'.format(endpoint_uid, priority))
            return
    else:
        taskqueue = TaskQueue.objects(organization=event.organization, team=event.team, priority=priority, tasks=task).first()
        if not taskqueue:
            app.logger.error('Task queue not found for task {}'.format(task_id))
            return
        taskqueue.modify(pull__tasks=task)
        task.modify(status='cancelled')
        app.logger.info('Waiting task cancelled')
        return

    if task.status == 'waiting':
        if taskqueue.running_task and taskqueue.running_task.id == task.id and str(endpoint.id) in TASK_THREADS:
            app.logger.critical('Waiting task to run')
            for i in range(20):
                task.reload('status')
                if task.status == 'running':
                    break
                time.sleep(0.1)
            else:
                app.logger.error('Waiting task to run timeouted out')
                taskqueue.modify(running_task=None)
                task.modify(status='cancelled')
        else:
            taskqueue.modify(running_task=None)
            taskqueue.modify(pull__tasks=task)
            task.modify(status='cancelled')
            app.logger.info('Waiting task cancelled without process running')
            return
    if task.status == 'running':
        if str(endpoint.id) in TASK_THREADS:
            if task.id in ROBOT_PROCESSES:
                taskqueue.modify(running_task=None)
                task.modify(status='cancelled')

                #os.kill(ROBOT_PROCESSES[task.id].pid, signal.CTRL_C_EVENT)
                ROBOT_PROCESSES[task.id].terminate()
                # del ROBOT_PROCESSES[task.id]  # will be done in the task loop when robot process exits
                app.logger.info('Running task cancelled with process running')
                return
            else:
                app.logger.error('Task process not found when cancelling task (%s)' % task_id)
        taskqueue.modify(running_task=None)
        task.modify(status='cancelled')
        app.logger.info('Running task cancelled without process running')

def event_handler_start_task(app, event):
    endpoint_uid = event.message['endpoint_uid']
    to_delete = event.message['to_delete'] if 'to_delete' in event.message else False
    organization = event.organization
    team = event.team

    endpoint = Endpoint.objects(organization=organization, team=team, uid=endpoint_uid).first()
    if not endpoint:
        org_name = team.organization.name + '-' + team.name if team else organization.name
        if not to_delete:
            app.logger.error('Endpoint not found for {}@{}'.format(org_name, endpoint_uid))
        return

    endpoint_id = str(endpoint.id)
    TASK_LOCK.acquire()
    if endpoint_id not in TASK_THREADS:
        TASK_THREADS[endpoint_id] = 1
        TASK_LOCK.release()
        reset_task_queue_status(app, organization, team)
        thread = threading.Thread(target=process_task_per_endpoint, args=(app, endpoint, organization, team), name='task_thread_per_endpoint')
        thread.daemon = True
        thread.start()
        #del TASK_THREADS[endpoint_id]  ## will delete when task loop exits
    else:
        TASK_THREADS[endpoint_id] = 2
        TASK_LOCK.release()
        app.logger.info('Schedule the task to the pending queue')

def event_handler_update_user_script(app, event):
    # TODO:
    return
    script = event.message['script']
    user = event.message['user']
    db_update_test(script=script, user=user)

EVENT_HANDLERS = {
    EVENT_CODE_START_TASK: event_handler_start_task,
    EVENT_CODE_CANCEL_TASK: event_handler_cancel_task,
    EVENT_CODE_UPDATE_USER_SCRIPT: event_handler_update_user_script,
}

def event_loop(app):
    eventqueue = EventQueue.objects().first()
    if not eventqueue:
        app.logger.error('event queue not found')

    app.logger.info('Event loop started')

    while True:
        try:
            event = eventqueue.pop()
        except pymongo.errors.AutoReconnect:
            app.logger.warning('polling event queue network error')
            event = None
        if not event:
            time.sleep(1)
            continue

        if isinstance(event, DBRef):
            app.logger.warning('event {} has been deleted, ignore it'.format(event.id))
            continue

        app.logger.info('Start to process event {} ...'.format(event.code))

        try:
            EVENT_HANDLERS[event.code](app, event)
            event.modify(status='Processed')
        except KeyError:
            app.logger.error('Unknown message: %s' % event.code)

def event_loop_parent(app):
    reset_event_queue_status(app)
    thread = threading.Thread(target=event_loop, args=(app,), name='event_loop')
    thread.daemon = True
    thread.start()
    thread.join()

def convert_json_to_robot_variable(args, variables, variable_file):
    local_args = None
    p = re.compile(r'\${(.*?)}')

    def var_replace(m):
        nonlocal local_args
        local_args.extend(m.groups(0))
        return '{}'

    with open(variable_file, 'w') as f:
        for k, v in variables.items():
            if isinstance(v, str):
                f.write(k + ' = ')
                local_args = []
                a = p.sub(var_replace, v)
                if len(local_args) > 0:
                    f.write('\'' + a + '\'.format(')
                    for arg in local_args:
                        f.write(arg + ', ')
                    f.write(')')
                else:
                    f.write('\'{}\''.format(v))
                f.write('\n')
            elif isinstance(v, list):
                f.write(k + ' = [')
                for vv in v:
                    local_args = []
                    a = p.sub(var_replace, vv)
                    if len(local_args) > 0:
                        f.write('\'' + a + '\'.format(')
                        for arg in local_args:
                            f.write(arg + ', ')
                        f.write('), ')
                    else:
                        f.write('\'{}\', '.format(vv))
                f.write(']\n')
            elif isinstance(v, dict):
                f.write(k + ' = {')
                for kk in v:
                    local_args = []
                    a = p.sub(var_replace, v[kk])
                    if len(local_args) > 0:
                        f.write('\'' + kk + '\': \'' + a + '\'.format(')
                        for arg in local_args:
                            f.write(arg + ', ')
                        f.write('), ')
                    else:
                        f.write('\'{}\': \'{}\', '.format(kk, v[kk]))
                f.write('}\n')

    args.extend(['--variablefile', str(variable_file)])

def process_task_per_endpoint(app, endpoint, organization=None, team=None):
    global ROBOT_PROCESSES, TASKS_CACHED

    if not organization and not team:
        app.logger.error('Argument organization and team must neither be None')
        return
    room_id = get_room_id(str(organization.id), str(team.id) if team else '')

    taskqueues = TaskQueue.objects(organization=organization, team=team, endpoint=endpoint)
    if taskqueues.count() == 0:
        app.logger.error('Taskqueue not found')
        return
    # taskqueues = [q for q in taskqueues]  # query becomes stale if the document it points to gets changed elsewhere, use document instead of query to perform deletion
    taskqueue_first = taskqueues.first()

    endpoint_id = str(endpoint.id)
    endpoint_uid = endpoint.uid
    org_name = team.organization.name + '-' + team.name if team else organization.name

    while True:
        taskqueue_first.reload('to_delete')
        if taskqueue_first.to_delete:
            taskqueues.delete()
            endpoint.delete()
            app.logger.info('Abort the task loop: {} @ {}'.format(org_name, endpoint_uid))
            break
        # TODO: lower priority tasks will take precedence if higher priority queue is empty first
        # but filled then when thread is searching for tasks in the lower priority task queues
        for priority in QUEUE_PRIORITY:
            exit_task = False
            for taskqueue in taskqueues:
                taskqueue.reload('to_delete')
                if taskqueue.to_delete:
                    exit_task = True
                    break
                if taskqueue.priority == priority:
                    break
            else:
                app.logger.error('Found task queue with unknown priority')
                continue

            if exit_task:
                break

            # "continue" to search for tasks in the lower priority task queues
            # "break" to start over to search for tasks from the top priority task queue
            task = taskqueue.pop()
            if not task:
                continue
            task_id = str(task.id)
            if isinstance(task, DBRef):
                app.logger.warning('task {} has been deleted, ignore it'.format(task_id))
                taskqueue.modify(running_task=None)
                break

            if task.kickedoff != 0 and not task.parallelization:
                app.logger.info('task has been taken over by other threads, do nothing')
                taskqueue.modify(running_task=None)
                break

            task.modify(inc__kickedoff=1)
            if task.kickedoff != 1 and not task.parallelization:
                app.logger.warning('a race condition happened')
                taskqueue.modify(running_task=None)
                break

            app.logger.info('Start to run task {} in the thread {}'.format(task_id, threading.current_thread().name))

            result_dir = get_test_result_path(task)
            scripts_dir = get_user_scripts_root(task)
            args = ['robot', '--loglevel', 'debug', '--outputdir', str(result_dir), '--extension', 'md',
                    '--consolecolors', 'on', '--consolemarkers', 'on']
            os.makedirs(result_dir)

            if hasattr(task, 'testcases'):
                for t in task.testcases:
                    args.extend(['-t', t])

            if hasattr(task, 'variables'):
                variable_file = Path(result_dir) / 'variablefile.py'
                convert_json_to_robot_variable(args, task.variables, variable_file)

            addr, port = '127.0.0.1', 8270
            args.extend(['-v', f'address_daemon:{addr}', '-v', f'port_daemon:{port}',
                        '-v', f'task_id:{task_id}', '-v', f'endpoint_uid:{endpoint_uid}'])
            args.append(os.path.join(scripts_dir, task.test.path, task.test.test_suite + '.md'))
            app.logger.info('Arguments: ' + str(args))

            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            ROBOT_PROCESSES[task.id] = p

            task.status = 'running'
            task.run_date = datetime.datetime.utcnow()
            task.endpoint_run = endpoint
            task.save()
            RPC_SOCKET.emit('task started', {'task_id': task_id}, room=room_id)

            log_msg = StringIO()
            if room_id not in ROOM_MESSAGES:
                ROOM_MESSAGES[room_id] = {task_id: log_msg}
            else:
                if task_id not in ROOM_MESSAGES[room_id]:
                    ROOM_MESSAGES[room_id][task_id] = log_msg
            ss = b''
            while True:
                c = p.stdout.read(1)
                if not c:
                    break
                try:
                    c = c.decode(encoding=sys.getdefaultencoding())
                except UnicodeDecodeError:
                    ss += c
                else:
                    c = '\r\n' if c == '\n' else c
                    log_msg.write(c)
                    RPC_SOCKET.emit('test report', {'task_id': task_id, 'message': c}, room=room_id)
            del ROBOT_PROCESSES[task.id]

            if ss != b'':
                log_msg_all = StringIO()
                try:
                    ss = ss.decode(chardet.detect(ss)['encoding'])
                except UnicodeDecodeError:
                    app.logger.warning(f'chardet error: {ss.decode("raw_unicode_escape")}')
                else:
                    log_msg_all.write(ss)
                log_msg_all.write(log_msg.getvalue())
                app.logger.info('\n' + log_msg_all.getvalue())
                RPC_SOCKET.emit('test report', {'task_id': task_id, 'message': ss}, room=room_id)
            else:
                app.logger.info('\n' + log_msg.getvalue())
            #app.logger.info('\n' + log_msg.getvalue().replace('\r\n', '\n'))

            p.wait()
            if p.returncode == 0:
                task.status = 'successful'
            else:
                task.reload('status')
                if task.status != 'cancelled':
                    task.status = 'failed'
            task.save()
            RPC_SOCKET.emit('task finished', {'task_id': task_id, 'status': task.status}, room=room_id)
            ROOM_MESSAGES[room_id][task_id].close()
            del ROOM_MESSAGES[room_id][task_id]
            if task_id in TASKS_CACHED:
                del TASKS_CACHED[task_id]

            taskqueue.modify(running_task=None)
            endpoint.modify(last_run_date=datetime.datetime.utcnow())

            if task.upload_dir:
                resource_dir_tmp = get_upload_files_root(task)
                if os.path.exists(resource_dir_tmp):
                    make_tarfile_from_dir(str(result_dir / 'resource.tar.gz'), resource_dir_tmp)

            result_dir_tmp = result_dir / 'temp'
            if os.path.exists(result_dir_tmp):
                shutil.rmtree(result_dir_tmp)

            notification_chain_call(task)
            # lately scheduled tasks before and after the count reset will be captured during re-polling queues
            TASK_LOCK.acquire()
            TASK_THREADS[endpoint_id] = 1
            TASK_LOCK.release()
            break
        else:
            TASK_LOCK.acquire()
            if TASK_THREADS[endpoint_id] != 1:
                TASK_THREADS[endpoint_id] = 1
                TASK_LOCK.release()
                app.logger.info('Run the lately scheduled task during polling queues')
                continue
            del TASK_THREADS[endpoint_id]
            TASK_LOCK.release()
            app.logger.info('Task processing exits')
            break

def check_endpoint(app, endpoint_uid, organization, team):
    org_name = team.organization.name + '-' + team.name if team else organization.name
    url = 'http://127.0.0.1:8270/{}'.format(endpoint_uid)
    server = xmlrpc.client.ServerProxy(url)
    endpoint = Endpoint.objects(uid=endpoint_uid, organization=organization, team=team).first()
    try:
        ret = server.get_keyword_names()
    except ConnectionRefusedError:
        err_msg = 'Endpoint {} @ {} connecting failed'.format(endpoint.name, org_name)
    except xmlrpc.client.Fault as e:
        err_msg = 'Endpoint {} @ {} RPC calling error'.format(endpoint.name, org_name)
        app.logger.exception(e)
    except TimeoutError:
        err_msg = 'Endpoint {} @ {} connecting timeouted'.format(endpoint.name, org_name)
    except OSError as e:
        err_msg = 'Endpoint {} @ {} unreachable'.format(endpoint.name, org_name)
    except Exception as e:
        err_msg = 'Endpoint {} @ {} has error:'.format(endpoint.name, org_name)
        app.logger.exception(e)
    else:
        if ret:
            if endpoint and endpoint.status == 'Offline':
                endpoint.modify(status='Online')
            return True
        else:
            err_msg = 'Endpoint {} @ {} RPC proxy not found'.format(endpoint.name, org_name)
    if endpoint and endpoint.status == 'Online':
        app.logger.error(err_msg)
        endpoint.modify(status='Offline')
    return False
    
def heartbeat_monitor(app):
    app.logger.info('Start endpoint online check thread')
    expires = 0
    while True:
        endpoints = Endpoint.objects()
        for endpoint in endpoints:
            check_endpoint(app, endpoint.uid, endpoint.organization, endpoint.team)
        time.sleep(30)

def normalize_url(url):
    if not url.startswith('/'):
        url = '/' + url
    if url.endswith('/'):
        url = url[:-1]
    return url

@RPC_APP.websocket('/msg')
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
            task = Task.objects(pk=task_id).first()
            TASKS_CACHED[task_id] = task
        else:
            task = TASKS_CACHED[task_id]
        room_id = get_room_id(str(task.organization.id), str(task.team.id) if task.team else '')
        RPC_SOCKET.emit('test log', {'task_id': task_id, 'message': data}, room=room_id)

@RPC_APP.websocket('/rpc')
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

    endpoint = Endpoint.objects(uid=uid).first()
    if endpoint:
        if endpoint.status == 'Forbidden' or endpoint.status == 'Unauthorized':
            await ws.send(endpoint.status)
            return
    organization = Organization.objects(pk=join_id).first()
    if not organization:
        team = Team.objects(pk=join_id).first()
        if not team:
            #await ws.send('Organization not found')
            return
    if not endpoint:
        try:
            endpoint = Endpoint(uid=uid, organization=team.organization if team else organization, team=team)
            endpoint.status = 'Unauthorized'
            endpoint.save()
        except ValidationError:
            print('Endpoint uid %s validation error' % uid)
            return
        print('Received a new endpoint with uid %s' % uid)
        return
    await ws.send('OK')

    def error_check(fut):
        try:
            fut.result()
        except websockets.exceptions.ConnectionClosedError as error:
            if len(rpc._request_table.keys()) != 0:
                print(f'Endpoint {url} was aborted, flushing pending tasks...')
                for k in rpc._request_table:
                    rpc._request_table[k].set_exception(RemoteCallError(error))
                rpc._request_table = {}
        except asyncio.exceptions.CancelledError:
            pass

    rpc = WebsocketRPC(ws, client_mode=True)
    rpc.client_task.add_done_callback(error_check)
    url = normalize_url(uid + '/' + backing_file)
    if url in RPC_PROXIES:
        await RPC_PROXIES[url].close()
        del RPC_PROXIES[url]
    RPC_PROXIES[url] = rpc
    print(f'Received an endpoint {url} connecting to {join_id}')

    try:
        await ws.wait_closed()
    except (CancelledError, ConnectionClosed):
        print(f'Endpoint {url} disconnected')

    if len(rpc._request_table.keys()) != 0:
        print(f'Endpoint {url} was closed, flushing pending tasks...')
        for k in rpc._request_table:
            rpc._request_table[k].set_exception(RemoteCallError(f'Endpoint {url} was closed'))
        rpc._request_table = {}

    try:
        await RPC_PROXIES[url].close()
    except websockets.exceptions.ConnectionClosedError:
        print(f'websocket close error for endpoint {url}')
    del RPC_PROXIES[url]

def restart_interrupted_tasks(app, organization=None, team=None):
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

def reset_event_queue_status(app):
    queue = EventQueue.objects().first()
    if not queue:
        queue = EventQueue()
        queue.save()
        app.logger.error('Event queue has not been created')

    ret = queue.modify({'rw_lock': True}, rw_lock=False)
    if ret:
        app.logger.info('Reset the read/write lock for event queue')

def reset_task_queue_status(app, organization=None, team=None):
    queues = TaskQueue.objects(organization=organization, team=team)
    if queues.count() == 0:
        app.logger.error('Task queue has not been created')
        return 1
    
    for q in queues:
        ret = q.modify({'rw_lock': True}, rw_lock=False)
        if ret:
            app.logger.info('Reset the read/write lock for queue {} with priority {}'.format(q.endpoint.uid, q.priority))
    return 0

def prepare_to_run(app, organization=None, team=None):
    ret = reset_event_queue_status(app)
    if ret:
        return ret

    ret = reset_task_queue_status(app, organization, team)
    if ret:
        return ret

    ret = restart_interrupted_tasks(app, organization, team)
    if ret:
        return ret

    return 0

def start_event_thread(app):
    task_thread = threading.Thread(target=event_loop_parent, name='event_loop_parent', args=(app,))
    task_thread.daemon = True
    task_thread.start()

def start_heartbeat_thread(app):
    thread = threading.Thread(target=heartbeat_monitor, name='heartbeat_monitor', args=(app,))
    thread.daemon = True
    thread.start()

def bootstrap_rpc_proxy(app):
    RPC_APP.run(host='0.0.0.0', port=5555, debug=True, protocol=WebSocketProtocol)

def start_rpc_proxy(app):
    app.logger.info('Start RPC proxy thread')
    thread = threading.Thread(target=bootstrap_rpc_proxy, name='rpc_proxy', args=(app,))
    thread.daemon = True
    thread.start()

    start_xmlrpc_server(app)

def start_xmlrpc_server(app):
    app.logger.info('Start local XML RPC server thread')
    thread = XMLRPCServer(RPC_PROXIES, host='0.0.0.0', port=8270)
    thread.daemon = True
    thread.start()

def initialize_runner(app):
    notification_chain_init(app)

if __name__ == '__main__':
    pass
