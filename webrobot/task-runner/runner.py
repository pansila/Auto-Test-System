import argparse
import multiprocessing
import threading
import os
import signal
import sys
import time
from pathlib import Path

import robot
from bson import DBRef
from mongoengine import connect

sys.path.insert(0, os.path.abspath('.'))
from app.main.model.database import (QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MAX,
                      QUEUE_PRIORITY_MIN, Task, TaskArchived, TaskQueue, Test)
from app.main.config import get_config

from util.notification import send_email

RESULT_DIR = Path(get_config().TEST_RESULT_ROOT)

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
    while True:
        for priority in (QUEUE_PRIORITY_MAX, QUEUE_PRIORITY_DEFAULT, QUEUE_PRIORITY_MIN):
            # print('checking priority {}'.format(priority))
            task = TaskQueue.pop(endpoint, priority)
            if task:
                if isinstance(task, DBRef):
                    print('task {} has been deleted, ignore it'.format(task.id))
                if task.kickedoff == 0:
                    task = Task.objects(pk=task.id).modify(new=True, inc__kickedoff=1)
                    if task.kickedoff != 1:
                        print('a race condition happened')
                    else:
                        print('\nStart to run task {} ...'.format(task.id))
                        # args = ['--loglevel', 'debug', '--outputdir', str(RESULT_DIR / str(task.id)), '--extension', 'md']
                        args = ['--outputdir', str(RESULT_DIR / str(task.id)), '--extension', 'md']

                        if hasattr(task, 'testcases'):
                            for t in task.testcases:
                                args.extend(['-t', t])

                        if hasattr(task, 'variables'):
                            for k, v in task.variables.items():
                                args.extend(['-v', '{}:{}'.format(k, v)])

                        addr, port = endpoint.split(':')
                        args.extend(['-v', 'address_daemon:{}'.format(addr), '-v', 'port_daemon:{}'.format(port),
                                    '-v', 'port_test:{}'.format(int(port)+1)])
                        args.append(task.test.path)

                        task.status = 'running'
                        task.save()

                        proc_queue = multiprocessing.Queue()
                        proc = multiprocessing.Process(target=run_task, args=(proc_queue, args))
                        proc.daemon = True
                        proc.start()
                        proc.join()

                        ret = proc_queue.get()
                        if ret == 0:
                            task.status = 'successful'
                        else:
                            task.status = 'failed'
                        task.save()

                        send_email(task)

                        TaskArchived.objects({}).modify(push__tasks=task)
                else:
                    print('task has been kicked off, just pop the task from the queue')
                break
        time.sleep(1)

def restart_interrupted_tasks():
    """
    Restart interrupted tasks that have been left over when task runner aborts
    """
    pass

def prepare_running_tasks():
    try:
        TaskArchived.objects({}).get()
    except TaskArchived.DoesNotExist:
        TaskArchived().save()
    
    restart_interrupted_tasks()

def listen_task():
    print('Start listening tasks from database 127.0.0.1:27017')

    prepare_running_tasks()

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

if __name__ == '__main__':
    connect(get_config().MONGODB_DATABASE)

    if len(sys.argv) < 2:
        listen_task()
        sys.exit(0)

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
