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
import traceback
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
QUIT_AFTER_IDLE_TIME = 1800  # seconds

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
                proc['process'].terminate()
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

def event_handler_exit_event_task(event):
    org_name = event.team.organization.name + '-' + event.team.name if event.team else event.organization.name
    print('Exit the event loop due to idle: {}'.format(org_name))
    return True

EVENT_HANDLERS = {
    EVENT_CODE_CANCEL_TASK: event_handler_cancel_task,
    EVENT_CODE_UPDATE_USER_SCRIPT: event_handler_update_user_script,
    EVENT_CODE_EXIT_EVENT_TASK: event_handler_exit_event_task
}

def event_loop(organization=None, team=None):
    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        print('Error: event queue not found')

    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start event loop: {}'.format(org_name))

    while True:
        eventqueue.update(inc__alive_counter=1)
        # to_delete is roloaded implicitly in eventqueue.pop()
        if eventqueue.to_delete:
            eventqueue.delete()
            print('Exit the event loop: {}'.format(org_name))
            break

        event = eventqueue.pop()
        if not event:
            continue

        if isinstance(event, DBRef):
            print('event {} has been deleted, ignore it'.format(event.id))
            continue

        event.organization = organization
        event.team = team
        event.save()

        print('\n{}: Start to process event {} ...'.format(org_name, event.code))
        try:
            ret = EVENT_HANDLERS[event.code](event)
            event.status = 'Processed'
            event.save()
        except KeyError:
            print('Unknown message: %s' % event.code)
        except Exception:
            print('Error happened during processing event: %s' % event.code)
            e_type, e_value, e_traceback = sys.exc_info()
            event.message['exception_type'] = e_type
            event.message['exception_value'] = e_value
            event.message['exception_traceback'] = traceback.print_tb(e_traceback)
            event.save()
        if ret:
            break

        time.sleep(1)

def event_loop_helper(organization=None, team=None):
    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        print('Error: event queue not found')
        eventqueue.modify(test_alive=False)
        return

    org_name = team.organization.name + '-' + team.name if team else organization.name

    thread = threading.Thread(target=event_loop, name='event_loop_' + org_name, args=(organization, team))
    thread.daemon = True
    thread.start()

    while thread.is_alive():
        thread.join(1)
    else:
        eventqueue.modify(test_alive=False)

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
    # taskqueues = [q for q in taskqueues]  # query becomes stale if the document it points to gets changed elsewhere, use document instead of query to perform deletion
    taskqueue_first = taskqueues[0]

    endpoints = Endpoint.objects(endpoint_address=endpoint_address, organization=organization, team=team)
    if endpoints.count() == 0:
        print('Endpoint not found')
        return

    eventqueue = EventQueue.objects(organization=organization, team=team).first()
    if not eventqueue:
        print('Event queue not found')
        return

    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start task loop: {} @ {}'.format(org_name, endpoint_address))

    while True:
        taskqueues.update(inc__alive_counter=1)
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
                taskqueue.update(inc__idle_counter=1)
                continue
            taskqueue.update(idle_counter=0)
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

            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
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
        else:
            min_idle = sys.maxsize
            for taskqueue in taskqueues:
                if taskqueue.idle_counter < min_idle:
                    min_idle = taskqueue.idle_counter
            if min_idle > QUIT_AFTER_IDLE_TIME:
                taskqueues.modify(test_alive=False)
                print('Exit task loop due to idle: {} @ {}'.format(org_name, endpoint_address))
                break
        time.sleep(1)

def task_loop_helper_per_endpoint(endpoint_address, organization=None, team=None):
    org_name = team.organization.name + '-' + team.name if team else organization.name

    taskqueue = TaskQueue.objects(organization=organization, team=team, endpoint_address=endpoint_address, priority=QUEUE_PRIORITY_DEFAULT).first()
    if not taskqueue:
        print('Error: task queue not found')
        taskqueue.modify(test_alive=False)
        return

    thread = threading.Thread(target=task_loop_per_endpoint,
                              name='task_loop_{}@{}'.format(org_name, endpoint_address),
                              args=(endpoint_address, organization, team))
    thread.daemon = True
    thread.start()

    while thread.is_alive():
        thread.join(1)
    else:
        taskqueue.modify(test_alive=False)

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

def start_event_thread(eventqueue, organization, team):
    eventqueue.events = []
    eventqueue.save()
    reset_event_queue_status(organization, team)
    task_thread = threading.Thread(target=event_loop_helper, name='event_loop_helper_' + org_name, args=(organization, team))
    task_thread.daemon = True
    task_thread.start()
    eventqueue.update(alive_counter=0)

def start_task_thread(taskqueue, organization, team):
    reset_task_queue_status(organization, team)
    task_thread = threading.Thread(target=task_loop_helper_per_endpoint,
                                   name='task_loop_helper_{}@{}'.format(org_name, taskqueue.endpoint_address),
                                   args=(taskqueue.endpoint_address, organization, team))
    task_thread.daemon = True
    task_thread.start()
    taskqueue.update(idle_counter=0, alive_counter=0)

def start_threads(task=None, organization=None, team=None):
    threads = []
    org_name = team.organization.name + '-' + team.name if team else organization.name
    print('Start monitoring threads for {}'.format(org_name))
    # ret = prepare_to_run(organization, team)
    # if ret:
    #     return ret

    eventqueue = EventQueue.objects(organization=organization, team=team).modify(test_alive=True)
    if not eventqueue:
        eventqueue = EventQueue(organization=organization, team=team)
        eventqueue.save()
    if not eventqueue.test_alive:
        start_event_thread(eventqueue, organization, team)
    else:
        alive_counter = eventqueue.alive_counter
        time.sleep(3)
        eventqueue.reload('alive_counter')
        if eventqueue.alive_counter == alive_counter:
            start_event_thread(eventqueue, organization, team)

    taskqueue = TaskQueue.objects(organization=organization, team=team, priority=QUEUE_PRIORITY_DEFAULT, endpoint_address__in=task.endpoint_list).modify(test_alive=True)
    if not taskqueue:
        print('Error: task queue not found')
        return
    if not taskqueue.test_alive:
        start_task_thread(taskqueue, organization, team)
    else:
        alive_counter = taskqueue.alive_counter
        time.sleep(3)
        taskqueue.reload('alive_counter')
        if taskqueue.alive_counter == alive_counter:
            start_task_thread(taskqueue, organization, team)

def _start_threads(task=None, organization=None, team=None):
    task_thread = threading.Thread(target=start_threads, name="start_threads", args=(task, organization, team))
    task_thread.daemon = True
    task_thread.start()

def start_threads_by_user(user):
    teams = []
    for organization in user.organizations:
        _start_threads(organization=organization)
        for team in organization.teams:
            _start_threads(organization=team.organization, team=team)
            teams.append(team)
    for team in user.teams:
        if team not in teams:
            _start_threads(organization=team.organization, team=team)

def start_threads_by_task(task):
    _start_threads(task=task, organization=task.organization, team=task.team)

def initialize_runner(user):
    notification_chain_init()

if __name__ == '__main__':
    pass
