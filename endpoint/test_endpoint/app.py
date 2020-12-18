# -*- coding: utf-8 -*-
import sys
import os
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-command help', dest='action')
    parser_add = subparsers.add_parser('add', help='install an app or the virtual environment')
    parser_add.add_argument('package', type=str, default=None,
                        help='install a python package by using poetry')
    parser_remove = subparsers.add_parser('remove', help='uninstall an app or the virtual environment')
    parser_remove.add_argument('package', type=str, default=None,
                        help='uninstall a python package by using poetry')
    parser.add_argument('--install', default=False, action='store_true',
                        help='install the virtual environments for the robotest endpoint')
    parser.add_argument('--uninstall', default=False, action='store_true',
                        help='uninstall the virtual environments for the robotest endpoint')
    parser.add_argument('--update', default=False, nargs='?', const=True, metavar='VERSION',
                        help='update the collie itself')
    parser.add_argument('--force', default=False, action='store_true',
                        help='force to update the collie itself')
    parser.add_argument('--debug', default=False, action='store_true',
                        help='enable the runtime log messages of tests')
    parser.add_argument('--host', type=str,
                        help='the server IP for the test endpoint daemon to connect')
    parser.add_argument('--port', type=int,
                        help='the server port for the test endpoint daemon to connect')
    parser.add_argument('--join_id',
                        help='the organization ID or team ID to join')
    args = parser.parse_args()

    if args.install:
        from test_endpoint.install import run_install
        run_install()
    elif args.uninstall:
        from test_endpoint.install import run_uninstall
        run_uninstall()
    elif args.update:
        from test_endpoint.update import SelfUpdate
        SelfUpdate(args.update, args.force).run()
    elif args.join_id:
        from test_endpoint.update import SelfUpdate
        SelfUpdate(args.update, args.force).update_join_id(args.join_id)
    elif 'action' in args and 'package' in args and args.package:
        from test_endpoint.venv_run import activate_workspace
        ws = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "workspace")
        with activate_workspace(ws):
            if args.action == 'add':
                subprocess.run('poetry add ' + args.package, shell=True, check=True)
            elif args.action == 'remove':
                subprocess.run('poetry remove ' + args.package, shell=True, check=True)
    else:
        from test_endpoint.venv_run import start
        start(args.host, args.port, args.debug)
    return 0
