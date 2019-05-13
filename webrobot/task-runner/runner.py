import argparse
import datetime
import multiprocessing
import os
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

sys.path.append('.')
from util.notification import send_email
from util.dbhelper import update_test
from app.main.config import get_config
from app.main.model.database import (EVENT_CODE_CANCEL_TASK, EVENT_CODE_UPDATE_USER_SCRIPT,
                                     QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_MIN,
                                     Event, EventQueue, Endpoint, Task, TaskArchived, TaskQueue, Test)


RESULT_DIR = Path(get_config().TEST_RESULT_ROOT)
ROBOT_TASKS = []

def make_tarfile(output_filename, source_dir):
    if output_filename[-2:] != 'gz':
        output_filename = output_filename + '.tar.gz'
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))

    return output_filename

def event_handler_cancel_task(event):
    address = event.message['address']
    priority = event.message['priority']
    task_id = event.message['task_id']

    if not TaskQueue.acquire_lock(address, priority):
        print('task locking timed out')
    else:
        try:
            t = Task.objects(pk=task_id).get()
        except Task.DoesNotExist:
            print('task not found for ' + task_id)
            TaskQueue.release_lock(address, priority)
        else:
            task = Task.objects(pk=task_id).get()
            if task.status == 'waiting':
                TaskQueue.objects(endpoint_address=address, priority=priority).update_one(pull__tasks=ObjectId(task_id))
                Task.objects(pk=task_id).update_one(status='cancelled')
            elif task.status == 'running':
                TaskQueue.objects(endpoint_address=address, priority=priority).modify(running_task=None)
                oid = ObjectId(task_id)
                for idx, task in enumerate(ROBOT_TASKS):
                    if task['task_id'] == oid:
                        task['process'].terminate()
                        del ROBOT_TASKS[idx]
                        break
                else:
                    print('task not found for ' + task_id)
        TaskQueue.release_lock(address, priority)

def event_handler_update_user_script(event):
    script = event.message['script']
    update_test(script=script)

def run_event_loop():
    global ROBOT_TASKS
    while True:
        try:
            eventqueue = EventQueue.objects.get()
        except EventQueue.DoesNotExist:
            print('event queue does not exist, please create it first')
            break
        except EventQueue.MultipleObjectsReturned:
            print('Error: multiple event queues found')
            break

        event = EventQueue.pop()
        if event:
            if isinstance(event, DBRef):
                print('event {} has been deleted, ignore it'.format(event.id))
                continue

            print('\nStart to process event {} ...'.format(event.code))
            if event.code == EVENT_CODE_CANCEL_TASK:
                event_handler_cancel_task(event)
            elif event.code == EVENT_CODE_UPDATE_USER_SCRIPT:
                event_handler_update_user_script(event)

        time.sleep(1)

def run_task(queue, args):
    exit_orig = sys.exit
    ret = 0
    def exit_new(r):
        nonlocal ret
        ret = r
    sys.exit = exit_new

    robot.run_cli(args)

    queue.put(ret)
    sys.exit = exit_orig

def run_task_for_endpoint(endpoint):
    global ROBOT_TASKS
    while True:
        for priority in (QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MIN):
            try:
                taskqueue = TaskQueue.objects(endpoint_address=endpoint, priority=priority).get()
            except TaskQueue.DoesNotExist:
                print('task queue has been deleted, exit the task loop')
                break
            except TaskQueue.MultipleObjectsReturned:
                print('Error: multiple task queues found')
                continue

            task = TaskQueue.pop(endpoint, priority)
            if task:
                if isinstance(task, DBRef):
                    print('task {} has been deleted, ignore it'.format(task.id))
                    continue
                if not TaskQueue.acquire_lock(endpoint, priority):
                    print('task queue locking timed out')
                    continue

                if task.kickedoff == 0 or task.parallelization:
                    task = Task.objects(pk=task.id).modify(new=True, inc__kickedoff=1)
                    if task.kickedoff != 1 and not task.parallelization:
                        print('a race condition happened')
                    else:
                        # if task.parallelization:
                        #     task = Task(task)
                        print('\nStart to run task {} ...'.format(task.id))
                        task.status = 'running'
                        task.run_date = datetime.datetime.utcnow()
                        task.endpoint_run = endpoint
                        task.save()

                        result_dir = RESULT_DIR / str(task.id)
                        args = ['--loglevel', 'debug', '--outputdir', str(result_dir), '--extension', 'md']
                        # args = ['--outputdir', str(result_dir), '--extension', 'md']
                        os.mkdir(result_dir)

                        if hasattr(task, 'testcases'):
                            for t in task.testcases:
                                args.extend(['-t', t])

                        if hasattr(task, 'variables'):
                            variable_file = Path(result_dir) / 'variablefile.py'
                            with open(variable_file, 'w') as f:
                                for k, v in task.variables.items():
                                    if isinstance(v, str):
                                        f.write('{} = \'{}\'\n'.format(k, v))
                                    else:
                                        f.write('{} = {}\n'.format(k, v))
                            args.extend(['--variablefile', variable_file])

                        addr, port = endpoint.split(':')
                        args.extend(['-v', 'address_daemon:{}'.format(addr), '-v', 'port_daemon:{}'.format(port),
                                    '-v', 'port_test:{}'.format(int(port)+1), '-v', 'task_id:{}'.format(task.id)])
                        args.append(task.test.path)

                        taskqueue.running_task = task
                        taskqueue.save()
                        TaskQueue.release_lock(endpoint, priority)

                        print('Arguments: ' + str(args))
                        proc_queue_read = multiprocessing.Queue()
                        proc = multiprocessing.Process(target=run_task, args=(proc_queue_read, args))
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

                        if not TaskQueue.acquire_lock(endpoint, priority):
                            print('task queue locking timed out, continue anyway')
                        taskqueue.running_task = None
                        taskqueue.save()
                        TaskQueue.release_lock(endpoint, priority)

                        try:
                            ep = Endpoint.objects(endpoint_address=endpoint).get()
                        except Endpoint.DoesNotExist:
                            print('No endpoint found with the address {}'.format(endpoint))
                        except Endpoint.MultipleObjectsReturned:
                            print('Multiple endpoints found with the address {}'.format(endpoint))
                        else:
                            ep.last_run_date = datetime.datetime.utcnow()
                            ep.save()

                        if task.upload_dir:
                            resource_dir_tmp = Path(get_config().UPLOAD_ROOT) / task.upload_dir
                            if resource_dir_tmp != '' and os.path.exists(resource_dir_tmp):
                                make_tarfile(str(result_dir / 'resource.tar.gz'), resource_dir_tmp)
                                # shutil.rmtree(resource_dir_tmp)

                        send_email(task)

                        TaskArchived.objects({}).modify(push__tasks=task)
                else:
                    print('task has been kicked off, do nothing but to pop the task from the queue')
                TaskQueue.release_lock(endpoint, priority)
                break
        time.sleep(1)

def restart_interrupted_tasks():
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

def prepare_running_tasks():
    try:
        TaskArchived.objects().get()
    except TaskArchived.DoesNotExist:
        TaskArchived().save()

    try:
        EventQueue.objects().get()
    except EventQueue.DoesNotExist:
        EventQueue().save()

    try:
        TaskQueue.objects().get()
    except TaskQueue.MultipleObjectsReturned:
        pass
    except TaskQueue.DoesNotExist:
        print('Error: Task Queue has not been created')
        return False
    
    restart_interrupted_tasks()

    return True

def listen_task():
    print('Start listening to tasks at database {}:{}'.format(get_config().MONGODB_URL,
                                                              get_config().MONGODB_PORT))

    if prepare_running_tasks() == False:
        return 1

    task_thread = threading.Thread(target=run_event_loop)
    task_thread.daemon = True
    task_thread.start()

    task_threads = []
    while True:
        taskqueues = TaskQueue.objects(priority=QUEUE_PRIORITY_DEFAULT).only('endpoint_address')
        running_endpoints = [ep for ep, t in task_threads] 
        for q in taskqueues:
            endpoint_address = q['endpoint_address']
            if endpoint_address not in running_endpoints:
                task_thread = threading.Thread(target=run_task_for_endpoint, args=(endpoint_address,))
                task_thread.daemon = True
                task_thread.start()
                task_threads.append((endpoint_address, task_thread))

        for i, el in enumerate(task_threads):
            ep, thread = el
            if not thread.is_alive():
                task_threads.pop(i)
                break

        time.sleep(1)
    return 0

if __name__ == '__main__':
    connect(get_config().MONGODB_DATABASE, host=get_config().MONGODB_URL, port=get_config().MONGODB_PORT)

    try:
        os.makedirs(RESULT_DIR)
    except FileExistsError:
        pass

    if len(sys.argv) < 2:
        ret = listen_task()
        sys.exit(ret)

    # if len(os.getcwd().split(os.path.sep)) < 2:
    #     print('Please run it in the server root directory')
    #     sys.exit(1)

    test_suite = sys.argv[1]

    try:
        test = Test.objects(test_suite=test_suite).get()
    except Test.DoesNotExist:
        print('Test suite {} not found in the database'.format(test_suite))
        print('Usage: {} <test_suite> [options]'.format(sys.argv[0]))
        sys.exit(1)
    except Test.MultipleObjectsReturned:
        print('Multiple Test suite {} found in the database'.format(test_suite))
        sys.exit(1)

    args = ['--outputdir', 'work_space', *sys.argv[2:], test.path]
    ret = robot.run_cli(args)
    sys.exit(ret)
