import argparse
import datetime
import multiprocessing
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

import robot
from bson import DBRef, ObjectId
from mongoengine import connect

from task_runner.util.notification import send_email
from task_runner.util.dbhelper import db_update_test
from app.main.util.tarball import make_tarfile
from app.main.config import get_config
from app.main.model.database import *
from app.main.util.request_parse import get_test_result_root


ROBOT_TASKS = []


def event_handler_cancel_task(event):
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
        taskqueue.modify(running_task=None)
        for idx, proc in enumerate(ROBOT_TASKS):
            if str(proc['task_id']) == task_id:
                proc['process'].terminate()
                del ROBOT_TASKS[idx]
                break
        else:
            print('task to cancel not found for ' + task_id)

def event_handler_update_user_script(event):
    script = event.message['script']
    user = event.message['user']
    db_update_test(script=script, user=user)


EVENT_HANDLERS = {
    EVENT_CODE_CANCEL_TASK: event_handler_cancel_task,
    EVENT_CODE_UPDATE_USER_SCRIPT: event_handler_update_user_script
}

def event_loop(organization=None, team=None):
    global ROBOT_TASKS # todo
    ret = EventQueue.find(organization, team)
    if not ret:
        print('Error: event queue not found')
    q, role = ret
    eventqueue = q.first()
    print('Start event loop: {}'.format(role.name))

    while True:
        event = eventqueue.pop()
        if event:
            if isinstance(event, DBRef):
                print('event {} has been deleted, ignore it'.format(event.id))
                continue

            print('\nStart to process event {} ...'.format(event.code))
            try:
                EVENT_HANDLERS[event.code](event)
            except KeyError:
                print('Unknown message: %s' % event.code)


        if q.first().to_delete:
            print('Exit the event loop')
            break
        time.sleep(1)

def event_loop_helper(organization=None, team=None):
    ret = EventQueue.find(organization, team)
    if not ret:
        return
    eventqueue, selector = ret

    thread = threading.Thread(target=event_loop, name='event_loop_' + selector.name, args=(organization, team))
    thread.daemon = True
    thread.start()

    while True:
        thread.join(1)
        if thread.is_alive():
            eventqueue.modify(test_alive=True)
        else:
            eventqueue.modify(test_alive=False)
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

    args.extend(['--variablefile', variable_file])

def run_robot_task(queue, args):
    exit_orig = sys.exit
    ret = 0
    def exit_new(r):
        nonlocal ret
        ret = r
    sys.exit = exit_new

    robot.run_cli(args)

    queue.put(ret)
    sys.exit = exit_orig

def task_loop_per_endpoint(endpoint_address, organization=None, team=None):
    global ROBOT_TASKS

    ret = TaskQueue.find(organization, team, endpoint_address)
    if not ret:
        print('Taskqueue not found')
        return
    taskqueues, role = ret

    ret = Endpoint.find(endpoint_address=endpoint_address, organization=organization, team=team)
    if not ret:
        print('Endpoint not found')
        return
    eps, _ = ret

    print('Start task loop: {} - {}'.format(role.name, endpoint_address))

    while True:
        if taskqueues.first().to_delete:
            taskqueues.delete()
            eps.delete()
            print('Exit task loop: {} - {}'.format(role.name, endpoint_address))
            break
        # TODO: lower priority tasks will take precedence if higher priority queue is empty first
        # but filled then when thread is searching for tasks in the lower priority task queues
        for priority in (QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MIN):
            for taskqueue in taskqueues:
                if taskqueue.priority == priority:
                    break

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

            result_dir = get_test_result_root(task)
            args = ['--loglevel', 'debug', '--outputdir', str(result_dir), '--extension', 'md']
            # args = ['--outputdir', str(result_dir), '--extension', 'md']
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

            taskqueue.modify(running_task=task)

            print('Arguments: ' + str(args))
            proc_queue_read = multiprocessing.Queue()
            proc = multiprocessing.Process(target=run_robot_task, args=(proc_queue_read, args))
            proc.daemon = True
            proc.start()

            ROBOT_TASKS.append({'task_id': task.id, 'process': proc, 'queue_read': proc_queue_read})
            proc.join()

            try:
                ret = proc_queue_read.get(timeout=1)
            except queue.Empty:
                pass
            else:
                if ret == 0:
                    task.status = 'successful'
                else:
                    task.status = 'failed'
                task.save()

            taskqueue.modify(running_task=None)

            try:
                ep = Endpoint.objects(endpoint_address=endpoint_address).get()
            except Endpoint.DoesNotExist:
                print('No endpoint found with the address {}'.format(endpoint_address))
            except Endpoint.MultipleObjectsReturned:
                print('Multiple endpoints found with the address {}'.format(endpoint_address))
            else:
                ep.last_run_date = datetime.datetime.utcnow()
                ep.save()

            if task.upload_dir:
                resource_dir_tmp = get_upload_files_root(task)
                if os.path.exists(resource_dir_tmp):
                    make_tarfile(str(result_dir / 'resource.tar.gz'), resource_dir_tmp)
                    shutil.rmtree(resource_dir_tmp)

            result_dir_tmp = result_dir / 'temp'
            if os.path.exists(result_dir_tmp):
                shutil.rmtree(result_dir_tmp)

            # TODO: notification chain
            send_email(task)
            break
        time.sleep(1)

def task_loop_helper_per_endpoint(endpoint_address, organization=None, team=None):
    ret = TaskQueue.find(organization, team, endpoint_address, priority=QUEUE_PRIORITY_DEFAULT)
    if not ret:
        return
    taskqueue, selector = ret

    thread = threading.Thread(target=task_loop_per_endpoint,
                              name='task_loop_{}_{}'.format(endpoint_address, selector.name),
                              args=(endpoint_address, organization, team))
    thread.daemon = True
    thread.start()

    while True:
        thread.join(1)
        if thread.is_alive():
            taskqueue.modify(test_alive=True)
        else:
            taskqueue.modify(test_alive=False)
            break

def restart_interrupted_tasks(organization=None, team=None):
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

def reset_event_queue_status(organization=None, team=None):
    for k, v in {'team': team, 'organization': organization}.items():
        if not v:
            continue
        queues = EventQueue.objects(**{k: v})
        if queues.count() > 0:
            break
    else:
        print('Error: Event queue has not been created')
        return 1

    for q in queues:
        ret = q.modify({'rw_lock': True}, rw_lock=False)
        if ret:
            print('Reset the read/write lock for event queue')
    return 0

def reset_task_queue_status(organization=None, team=None):
    for k, v in {'team': team, 'organization': organization}.items():
        if not v:
            continue
        queues = TaskQueue.objects(**{k: v})
        if queues.count() > 0:
            break
    else:
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
    print('Start monitoring tasks for organization/team: {}/{}'.format(organization.name if organization else '',
                                                            team.name if team else ''))
    # ret = prepare_to_run(organization, team)
    # if ret:
    #     return ret

    ret = EventQueue.find(organization, team)
    if not ret:
        eventqueue = EventQueue(organization=organization, team=team)
        eventqueue.save()
        ret = EventQueue.find(organization, team)
        if not ret:
            print('Error: event queue not found')
            return
    eventqueue, selector = ret
    eventqueue.modify(test_alive=False)
    time.sleep(3) # test_alive will be set to True in a second if it's alive
    if not eventqueue.first().test_alive:
        reset_event_queue_status(organization, team)
        task_thread = threading.Thread(target=event_loop_helper, name='event_loop_helper' + selector.name, args=(organization, team))
        task_thread.daemon = True
        task_thread.start()

    ret = TaskQueue.find(organization, team, priority=QUEUE_PRIORITY_DEFAULT)
    if not ret:
        return
    taskqueues, selector = ret
    taskqueues.update(test_alive=False)
    time.sleep(3) # test_alive will be set to True in a second if it's alive
    for q in taskqueues:
        if not q.test_alive:
            reset_task_queue_status(organization, team)
            task_thread = threading.Thread(target=task_loop_helper_per_endpoint,
                                           name='task_loop_helper_{}_{}'.format(q.endpoint_address, selector.name),
                                           args=(q.endpoint_address, organization, team))
            task_thread.daemon = True
            task_thread.start()

def start_threads(organization=None, team=None):
    task_thread = threading.Thread(target=monitor_threads, name="monitor_threads", args=(organization, team))
    task_thread.daemon = True
    task_thread.start()

if __name__ == '__main__':
    pass
