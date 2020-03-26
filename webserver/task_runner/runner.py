import argparse
import asyncio
import datetime
import eventlet
import functools
import os
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

import mongoengine
from bson import DBRef, ObjectId
from mongoengine import connect

from app.main.config import get_config
from app.main.model.database import *
from app.main.util.get_path import get_test_result_path, get_upload_files_root
from app.main.util.tarball import make_tarfile
from app.main.util import get_room_id
from task_runner.util.dbhelper import db_update_test
from task_runner.util.notification import (notification_chain_call,
                                           notification_chain_init)

ROBOT_PROCESSES = {}  # {task id: process instance}
TASK_THREADS = {}     # {taskqueue id: idle counter (int)}}
TASK_LOCK = threading.Lock()

QUIT_AFTER_IDLE_TIME = 1800 * len(QUEUE_PRIORITY)  # seconds, count three times in a time of task searching


ROOM_MESSAGES = {}  # {"organziation:team": old_message, new_message}

async def event_handler_cancel_task(app, event):
    global ROBOT_PROCESSES, TASK_THREADS
    address = event.message['address']
    priority = event.message['priority']
    task_id = event.message['task_id']

    taskqueue = TaskQueue.objects(organization=event.organization, team=event.team, endpoint_address=address, priority=priority).first()
    if not taskqueue:
        app.logger.error('Task queue not found for {}:{}'.format(address, priority))
        return

    endpoint = Endpoint.objects(endpoint_address=address, organization=organization, team=team).first()
    if not endpoint:
        app.logger.error('Endpoint not found for {}'.format(address))
        return

    task = Task.objects(pk=task_id).first()
    if not task:
        app.logger.error('Task not found for ' + task_id)
        return

    if task.status == 'waiting':
        if taskqueue.running_task and taskqueue.running_task.id == task.id and str(endpoint.id) in TASK_THREADS:
            app.logger.critical('Waiting task to run')
            for i in range(20):
                task.reload('status')
                if task.status == 'running':
                    break
                await asyncio.sleep(0.1)
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

async def event_handler_start_task(app, event):
    address = event.message['address']
    to_delete = event.message['to_delete'] if 'to_delete' in event.message else False
    organization = event.organization
    team = event.team

    endpoint = Endpoint.objects(organization=organization, team=team, endpoint_address=address).first()
    if not endpoint:
        org_name = team.organization.name + '-' + team.name if team else organization.name
        if not to_delete:
            app.logger.error('Endpoint not found for {}@{}'.format(org_name, address))
        return

    endpoint_id = str(endpoint.id)
    if endpoint_id not in TASK_THREADS:
        TASK_THREADS[endpoint_id] = True
        reset_task_queue_status(app, organization, team)
        await process_task_per_endpoint(app, address, organization, team)
        #del TASK_THREADS[endpoint_id]  ## will delete in the done callback

def event_handler_start_task_done(app, event):
    address = event.message['address']
    to_delete = event.message['to_delete'] if 'to_delete' in event.message else False
    organization = event.organization
    team = event.team

    endpoint = Endpoint.objects(organization=organization, team=team, endpoint_address=address).first()
    if not endpoint:
        org_name = team.organization.name + '-' + team.name if team else organization.name
        if not to_delete:
            app.logger.error('Endpoint not found for {}@{}'.format(org_name, address))
        return

    endpoint_id = str(endpoint.id)
    del TASK_THREADS[endpoint_id]

async def event_handler_update_user_script(app, event):
    script = event.message['script']
    user = event.message['user']
    db_update_test(script=script, user=user)

EVENT_HANDLERS = {
    EVENT_CODE_START_TASK: (event_handler_start_task, event_handler_start_task_done),
    EVENT_CODE_CANCEL_TASK: (event_handler_cancel_task, None),
    EVENT_CODE_UPDATE_USER_SCRIPT: (event_handler_update_user_script, None),
}

def log_event_exception(app, event, future):
    try:
        future.result()
    except Exception as e:
        app.logger.exception('Error happened during processing event: %s' % event.code)
        e_type, e_value, e_traceback = sys.exc_info()
        event.message['exception_type'] = str(e_type)
        event.message['exception_value'] = str(e_value)
        temp = StringIO()
        traceback.print_tb(e_traceback, file=temp)
        event.message['exception_traceback'] = temp.getvalue()
        temp.close()
        event.save()
    finally:
        if EVENT_HANDLERS[event.code][1]:
            EVENT_HANDLERS[event.code][1](app, event)

async def event_loop(app):
    eventqueue = EventQueue.objects().first()
    if not eventqueue:
        app.logger.error('event queue not found')

    app.logger.info('Event loop started')

    while True:
        event = await eventqueue.async_pop()
        if not event:
            await asyncio.sleep(1)
            continue

        if isinstance(event, DBRef):
            app.logger.warning('event {} has been deleted, ignore it'.format(event.id))
            continue

        app.logger.info('\nStart to process event {} ...'.format(event.code))

        try:
            async_task = asyncio.create_task(EVENT_HANDLERS[event.code][0](app, event))
            event.modify(status='Processed')
            async_task.add_done_callback(functools.partial(log_event_exception, app, event))
        except KeyError:
            app.logger.error('Unknown message: %s' % event.code)

def event_loop_parent(app):
    reset_event_queue_status(app)
    if os.name == 'nt':
        # Subprocesses are not supported for default loop of SelectorEventLoop on Windows
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(event_loop(app))
        loop.close()
    else:
        asyncio.run(event_loop(app))

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

async def process_task_per_endpoint(app, endpoint_address, organization=None, team=None):
    global ROBOT_PROCESSES

    if not organization and not team:
        app.logger.error('Argument organization and team must neither be None')
        return
    room_id = get_room_id(str(organization.id), str(team.id) if team else '')
    socketio = app.config['socketio']

    taskqueues = TaskQueue.objects(organization=organization, team=team, endpoint_address=endpoint_address)
    if taskqueues.count() == 0:
        app.logger.error('Taskqueue not found')
        return
    # taskqueues = [q for q in taskqueues]  # query becomes stale if the document it points to gets changed elsewhere, use document instead of query to perform deletion
    taskqueue_first = taskqueues.first()

    endpoints = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team)
    if endpoints.count() == 0:
        app.logger.error('Endpoint not found')
        return

    org_name = team.organization.name + '-' + team.name if team else organization.name

    while True:
        taskqueue_first.reload('to_delete')
        if taskqueue_first.to_delete:
            taskqueues.delete()
            endpoints.delete()
            app.logger.info('Abort the task loop: {} @ {}'.format(org_name, endpoint_address))
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
            task = await taskqueue.async_pop()
            if not task:
                continue
            if isinstance(task, DBRef):
                app.logger.warning('task {} has been deleted, ignore it'.format(task.id))
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

            app.logger.info('Start to run task {} ...'.format(task.id))

            result_dir = get_test_result_path(task)
            args = ['--loglevel', 'debug', '--outputdir', str(result_dir), '--extension', 'md',
                    '--consolecolors', 'on', '--consolemarkers', 'on']
            os.makedirs(result_dir)

            if hasattr(task, 'testcases'):
                for t in task.testcases:
                    args.extend(['-t', t])

            if hasattr(task, 'variables'):
                variable_file = Path(result_dir) / 'variablefile.py'
                convert_json_to_robot_variable(args, task.variables, variable_file)

            addr, port = endpoint_address.split(':')
            args.extend(['-v', 'address_daemon:{}'.format(addr), '-v', 'port_daemon:{}'.format(port),
                        '-v', 'port_test:{}'.format(int(port)+1), '-v', 'task_id:{}'.format(task.id)])
            args.append(task.test.path)
            app.logger.info('Arguments: ' + str(args))

            p = await asyncio.create_subprocess_exec('robot', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, limit=1,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            ROBOT_PROCESSES[task.id] = p

            task.status = 'running'
            task.run_date = datetime.datetime.utcnow()
            task.endpoint_run = endpoint_address
            task.save()
            socketio.emit('task started', {'task_id': str(task.id)}, room=room_id)

            log_msg = StringIO()
            if room_id not in ROOM_MESSAGES:
                ROOM_MESSAGES[room_id] = {str(task.id): log_msg}
            else:
                if str(task.id) not in ROOM_MESSAGES[room_id]:
                    ROOM_MESSAGES[room_id][str(task.id)] = log_msg
            while True:
                c = await p.stdout.read(1)
                if not c:
                    break
                c = c.decode()
                c = '\r\n' if c == '\n' else c
                log_msg.write(c)
                socketio.emit('console log', {'task_id': str(task.id), 'message': c}, room=room_id)
            del ROBOT_PROCESSES[task.id]

            app.logger.info('\n' + log_msg.getvalue())
            #app.logger.info('\n' + log_msg.getvalue().replace('\r\n', '\n'))

            await p.wait()
            if p.returncode == 0:
                task.status = 'successful'
            else:
                task.reload('status')
                if task.status != 'cancelled':
                    task.status = 'failed'
            task.save()
            socketio.emit('task finished', {'task_id': str(task.id), 'status': task.status}, room=room_id)
            ROOM_MESSAGES[room_id][str(task.id)].close()
            del ROOM_MESSAGES[room_id][str(task.id)]

            taskqueue.modify(running_task=None)

            endpoint = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team).first()
            if not endpoint:
                app.logger.error('No endpoint found with the address {}'.format(endpoint_address))
            else:
                endpoint.last_run_date = datetime.datetime.utcnow()
                endpoint.save()

            if task.upload_dir:
                resource_dir_tmp = get_upload_files_root(task)
                if os.path.exists(resource_dir_tmp):
                    make_tarfile(str(result_dir / 'resource.tar.gz'), resource_dir_tmp)

            result_dir_tmp = result_dir / 'temp'
            if os.path.exists(result_dir_tmp):
                shutil.rmtree(result_dir_tmp)

            notification_chain_call(task)
            break
        else:
            break

def check_endpoint(app, endpoint_address, organization, team):
    org_name = team.organization.name + '-' + team.name if team else organization.name
    url = 'http://{}'.format(endpoint_address)
    server = xmlrpc.client.ServerProxy(url)
    endpoint = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team).first()
    try:
        server.get_keyword_names()
    except ConnectionRefusedError:
        app.logger.error('Endpoint {} @ {} connecting failed'.format(org_name, endpoint_address))
    except xmlrpc.client.Fault as e:
        app.logger.error('Endpoint {} @ {} RPC calling error'.format(org_name, endpoint_address))
        app.logger.exception(e)
    except TimeoutError:
        app.logger.error('Endpoint {} @ {} connecting timeouted'.format(org_name, endpoint_address))
    except OSError as e:
        app.logger.error('Endpoint {} @ {} unreachable'.format(org_name, endpoint_address))
    except Exception as e:
        app.logger.error('Endpoint {} @ {} has error:'.format(org_name, endpoint_address))
        app.logger.exception(e)
    else:
        if endpoint and endpoint.status == 'Offline':
            endpoint.modify(status='Online')
        return True
    if endpoint and endpoint.status == 'Online':
        endpoint.modify(status='Offline')
    return False
    
def heartbeat_monitor(app):
    app.logger.info('Start endpoint online check thread')
    expires = 0
    while True:
        endpoints = Endpoint.objects()
        for endpoint in endpoints:
            check_endpoint(app, endpoint.endpoint_address, endpoint.organization, endpoint.team)
        time.sleep(30)
    
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
            app.logger.info('Reset the read/write lock for queue {} with priority {}'.format(q.endpoint_address, q.priority))
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

def initialize_runner(user):
    notification_chain_init()

if __name__ == '__main__':
    pass
