import argparse
import datetime
import subprocess
import os
import re
import queue
import shutil
import signal
import sys
import tarfile
import threading
import time
from pathlib import Path

import mongoengine
from bson import DBRef, ObjectId
from mongoengine import connect

from task_runner.util.notification import notification_chain_call, notification_chain_init
from task_runner.util.dbhelper import db_update_test
from app.main.util.tarball import make_tarfile
from app.main.config import get_config
from app.main.model.database import *
from app.main.util.get_path import get_test_result_path, get_upload_files_root


ROBOT_TASKS = []


def event_handler_cancel_task(event):
    global ROBOT_TASKS
    address = event.message['address']
    priority = event.message['priority']
    task_id = event.message['task_id']

    task = Task.objects(pk=task_id).first()
    if not task:
        print('task not found for ' + task_id)
        return

    taskqueue = TaskQueue.objects(endpoint_address=address, priority=priority).first()
    if not taskqueue:
        print('task queue not found for %s %s' % (address, priority))
        return

    if task.status == 'waiting':
        taskqueue.modify(pull__tasks=task)
        task.modify(status='cancelled')
    elif task.status == 'running':
        for idx, proc in enumerate(ROBOT_TASKS):
            if str(proc['task_id']) == task_id:
                taskqueue.modify(running_task=None)
                task.modify(status='cancelled')

                # os.kill(proc['process'].pid, signal.SIGTERM)
                proc['process'].kill()
                del ROBOT_TASKS[idx]
                break
        else:
            print('task to cancel not found for id %s in the task threads' % task_id)
            taskqueue.modify(running_task=None)
            task.modify(status='cancelled')

def event_handler_update_user_script(event):
    script = event.message['script']
    user = event.message['user']
    db_update_test(script=script, user=user)


EVENT_HANDLERS = {
    EVENT_CODE_CANCEL_TASK: event_handler_cancel_task,
    EVENT_CODE_UPDATE_USER_SCRIPT: event_handler_update_user_script
}

def event_loop(organization=None, team=None):
    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        print('Error: event queue not found')

    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start event loop: {}'.format(org_name))

    while True:
        event = eventqueue.pop()
        if event:
            if isinstance(event, DBRef):
                print('event {} has been deleted, ignore it'.format(event.id))
                continue

            print('\n{}: Start to process event {} ...'.format(org_name, event.code))
            try:
                EVENT_HANDLERS[event.code](event)
            except KeyError:
                print('Unknown message: %s' % event.code)

        # to_delete is roloaded implicitly in eventqueue.pop()
        if eventqueue.to_delete:
            eventqueue.delete()
            print('Exit the event loop: {}'.format(org_name))
            break
        time.sleep(1)

def event_loop_helper(organization=None, team=None):
    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        return

    org_name = team.organization.name + '-' + team.name if team else organization.name

    thread = threading.Thread(target=event_loop, name='event_loop_' + org_name, args=(organization, team))
    thread.daemon = True
    thread.start()

    while True:
        thread.join(1)
        if thread.is_alive():
            eventqueue.modify(test_alive=True)
        else:
            break

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

def task_loop_per_endpoint(endpoint_address, organization=None, team=None):
    global ROBOT_TASKS

    if not organization and not team:
        print('Argument organization and team must neither be None')
        return

    taskqueues = TaskQueue.objects(organization=organization, team=team, endpoint_address=endpoint_address)
    if taskqueues.count() == 0:
        print('Taskqueue not found')
        return
    taskqueus = [q for q in taskqueues]  # query becomes stale if the document it points to gets changed elsewhere, use document instead of query to perform deletion
    taskqueue_first = taskqueues[0]

    endpoints = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team)
    if endpoints.count() == 0:
        print('Endpoint not found')
        return

    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start task loop: {} @ {}'.format(org_name, endpoint_address))

    while True:
        taskqueue_first.reload('to_delete')
        if taskqueue_first.to_delete:
            for taskqueue in taskqueues:
                taskqueue.delete()
            endpoints.delete()
            print('Exit task loop: {} @ {}'.format(org_name, endpoint_address))
            break
        # TODO: lower priority tasks will take precedence if higher priority queue is empty first
        # but filled then when thread is searching for tasks in the lower priority task queues
        for priority in (QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MIN):
            for taskqueue in taskqueues:
                if taskqueue.priority == priority:
                    break
            else:
                print('Error: Found task queue with unknown priority')

            # "continue" to search for tasks in the lower priority task queue
            # "break" to start over to search for tasks from top priority task queue
            task = taskqueue.pop()
            if not task:
                continue
            if isinstance(task, DBRef):
                print('task {} has been deleted, ignore it'.format(task.id))
                break

            if task.kickedoff != 0 and not task.parallelization:
                print('task has been taken over by other threads, do nothing')
                break

            task.modify(inc__kickedoff=1)
            if task.kickedoff != 1 and not task.parallelization:
                print('a race condition happened')
                break

            print('\nStart to run task {} ...'.format(task.id))
            task.status = 'running'
            task.run_date = datetime.datetime.utcnow()
            task.endpoint_run = endpoint_address
            task.save()

            result_dir = get_test_result_path(task)
            args = ['robot', '--loglevel', 'debug', '--outputdir', str(result_dir), '--extension', 'md']
            # args = ['robot', '--outputdir', str(result_dir), '--extension', 'md']
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
            print('Arguments: ' + str(args))

            taskqueue.modify(running_task=task)

            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
            ROBOT_TASKS.append({'task_id': task.id, 'process': p})
            stdout, stderr = p.communicate()
            try:
                print(stdout.decode())
            except UnicodeDecodeError:
                print(stdout)

            # tempstr = b''
            # while p.poll() is None:
            #     inchar = p.stdout.read(1)
            #     if inchar:
            #         try:
            #             print(tempstr.decode(), end='', flush=True)
            #             print(inchar.decode(), end='', flush=True)
            #         except UnicodeDecodeError:
            #             tempstr += inchar
            #         else:
            #             tempstr = b''
            # else:
            #     print(p.stdout.read().decode().rstrip())
            #     break

            if p.returncode == 0:
                task.status = 'successful'
            else:
                task.status = 'failed'
            task.save()

            taskqueue.modify(running_task=None)

            endpoint = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team).first()
            if not endpoint:
                print('No endpoint found with the address {}'.format(endpoint_address))
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
        time.sleep(1)

def task_loop_helper_per_endpoint(endpoint_address, organization=None, team=None):
    org_name = team.organization.name + '-' + team.name if team else organization.name

    taskqueue = TaskQueue.objects(organization=organization, team=team, endpoint_address=endpoint_address, priority=QUEUE_PRIORITY_DEFAULT).first()
    if not taskqueue:
        return

    thread = threading.Thread(target=task_loop_per_endpoint,
                              name='task_loop_{}@{}'.format(org_name, endpoint_address),
                              args=(endpoint_address, organization, team))
    thread.daemon = True
    thread.start()

    while True:
        thread.join(1)
        if thread.is_alive():
            taskqueue.modify(test_alive=True)
        else:
            break

def restart_interrupted_tasks(organization=None, team=None):
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

def reset_event_queue_status(organization=None, team=None):
    queues = EventQueue.objects(organization=organization, team=team)
    if queues.count() == 0:
        print('Error: Event queue has not been created')
        return 1

    for q in queues:
        ret = q.modify({'rw_lock': True}, rw_lock=False)
        if ret:
            print('Reset the read/write lock for event queue')
    return 0

def reset_task_queue_status(organization=None, team=None):
    queues = TaskQueue.objects(organization=organization, team=team)
    if queues.count() == 0:
        print('Error: Task queue has not been created')
        return 1
    
    for q in queues:
        ret = q.modify({'rw_lock': True}, rw_lock=False)
        if ret:
            print('Reset the read/write lock for queue {} with priority {}'.format(q.endpoint_address, q.priority))
    return 0

def prepare_to_run(organization=None, team=None):
    ret = reset_event_queue_status(organization, team)
    if ret:
        return ret

    ret = reset_task_queue_status(organization, team)
    if ret:
        return ret

    ret = restart_interrupted_tasks(organization, team)
    if ret:
        return ret

    return 0

def monitor_threads(organization=None, team=None):
    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start monitoring tasks for {}'.format(org_name))
    # ret = prepare_to_run(organization, team)
    # if ret:
    #     return ret

    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        eventqueue = EventQueue(organization=organization, team=team)
        eventqueue.save()
    eventqueue.modify(test_alive=False)
    time.sleep(3) # test_alive will be set to True in a second if it's alive
    eventqueue.reload('test_alive')
    if not eventqueue.test_alive:
        reset_event_queue_status(organization, team)
        task_thread = threading.Thread(target=event_loop_helper, name='event_loop_helper_' + org_name, args=(organization, team))
        task_thread.daemon = True
        task_thread.start()

    taskqueues = TaskQueue.objects(organization=organization, team=team, priority=QUEUE_PRIORITY_DEFAULT)
    if taskqueues.count() == 0:
        return
    taskqueues.update(test_alive=False)
    time.sleep(3) # test_alive will be set to True in a second if it's alive
    for taskqueue in taskqueues:
        taskqueue.reload('test_alive')
        if not taskqueue.test_alive:
            reset_task_queue_status(organization, team)
            task_thread = threading.Thread(target=task_loop_helper_per_endpoint,
                                           name='task_loop_helper_{}@{}'.format(org_name, taskqueue.endpoint_address),
                                           args=(taskqueue.endpoint_address, organization, team))
            task_thread.daemon = True
            task_thread.start()

def _start_threads(organization=None, team=None):
    task_thread = threading.Thread(target=monitor_threads, name="monitor_threads", args=(organization, team))
    task_thread.daemon = True
    task_thread.start()

def start_threads(user):
    teams = []
    for organization in user.organizations:
        _start_threads(organization=organization)
        for team in organization.teams:
            _start_threads(organization=team.organization, team=team)
            teams.append(team)
    for team in user.teams:
        if team not in teams:
            _start_threads(organization=team.organization, team=team)

    notification_chain_init()

if __name__ == '__main__':
    pass
