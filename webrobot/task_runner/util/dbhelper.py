import argparse
import copy
import datetime
import os
import sys
from os import path
from pathlib import Path

import mistune
from mongoengine import *

sys.path.append('.')
from app.main.model.database import Test, User
from app.main.config import get_config

def filter_kw(item):
    item = item.strip()
    if item.startswith('${') or item.startswith('@{') or item.startswith('&{'):
        item = item[2:]
        if not item.endswith('}'):
            print('{ } mismatch for ' + item)
        else:
            item = item[0:-1]
    return item

def db_update_test(scripts_dir=None, script=None, user=None, organization=None, team=None):
    if scripts_dir is None:
        return 1
    found = False

    test_suites = []
    for root, dirs, files in os.walk(scripts_dir):
        for md_file in files:
            if not md_file.endswith('.md'):
                continue

            if script:
                match = True
                file_path = str(Path(root) / md_file).split(os.path.sep)
                file_path.reverse()
                script_path = str(Path(script)).split(os.path.sep)
                script_path.reverse()
                for i in range(len(script_path)):
                    if script_path[i] != file_path[i]:
                        match = False
                if not match:
                    continue

            if script:
                found = True

            test_suite = md_file.split('.')[0]
            test = Test()
            test.test_suite = test_suite
            test.test_cases = []
            test.organization = organization
            test.team = team
            test.author = User.objects(email=user).first()

            test_suites.append(test_suite)

            md_file = path.abspath(path.join(root, md_file))
            test.path = md_file
            with open(md_file) as f:
                parser = mistune.BlockLexer()
                text = f.read()
                parser.parse(mistune.preprocessing(text))
                for t in parser.tokens:
                    if t["type"] == "table":
                        table_header = t["header"][0].lower()
                        if table_header == 'test case' or table_header == 'test cases':
                            for c in t["cells"]:
                                if not c[0] == '---':
                                    test.test_cases.append(c[0])
                                    break
                        if table_header == 'variable' or table_header == 'variables':
                            list_var = None
                            for c in t["cells"]:
                                if c[0].startswith('#') or c[0].startswith('---'):
                                    continue
                                if c[0].startswith('${'):
                                    list_var = None
                                    dict_var = None
                                    test.variables[filter_kw(c[0])] = c[1]
                                elif c[0].startswith('@'):
                                    dict_var = None
                                    list_var = filter_kw(c[0])
                                    test.variables[list_var] = c[1:]
                                elif c[0].startswith('...'):
                                    if list_var:
                                        test.variables[list_var].extend(c[1:])
                                    elif dict_var:
                                        for i in c[1:]:
                                            if not i:
                                                continue
                                            k, v = i.split('=')
                                            test.variables[dict_var][k] = v
                                elif c[0].startswith('&'):
                                    list_var = None
                                    dict_var = filter_kw(c[0])
                                    test.variables[dict_var] = {}
                                    for i in c[1:]:
                                        if not i:
                                            continue
                                        k, v = i.split('=')
                                        test.variables[dict_var][k] = v
                                else:
                                    print('Unknown tag: ' + c[0])
            old_test = Test.objects(path=test.path).first()
            if not old_test:
                test.create_date = datetime.datetime.utcnow()
                test.save()
                print('Added new test suite {} to database'.format(test_suite))
                continue

            if old_test != test:
                print('Update test suite {}'.format(test_suite))
                for name in test:
                    if name == 'id' or name.startswith('_') or callable(test[name]):
                        continue
                    if name == 'author' or name == 'create_date' or name == 'update_date':
                        continue
                    if old_test[name] == test[name]:
                        continue
                    print('    Updating key: {}, {} -> {}'.format(name, old_test[name], test[name]))
                    old_test[name] = test[name]
                old_test.update_date = datetime.datetime.utcnow()
                old_test.save()
            if not old_test.author:
                old_test.author = test.author
                old_test.save()
            if not old_test.create_date:
                old_test.create_date = datetime.datetime.utcnow()
                old_test.save()


    # clean up stale test suites
    for test_old in Test.objects({}):
        for test_new in test_suites:
            if test_new == test_old.test_suite:
                break
        else:
            if script is None:
                Test.objects(pk=test_old.id).modify(remove=True)
                print('Remove stale test suite {}'.format(test_old.test_suite))

    if script and not found:
        return 1
    return 0

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', type=str, required=True,
                    help='specify an action to run',
                    choices=['CREATE', 'READ', 'UPDATE', 'DELETE'])
    parser.add_argument('--scripts', type=str,
                    help='specify the root folder of robot scripts, required if action=UPDATE')
    args = parser.parse_args()

    connect(get_config().MONGODB_DATABASE, host=get_config().MONGODB_URL, port=get_config().MONGODB_PORT)

    if args.action == 'READ':
        test_suites = Test.objects({})
        print([t.test_suite for t in test_suites])
    elif args.action == 'UPDATE':
        if args.scripts:
            ret = update_test(scripts_dir=args.scripts)
            sys.exit(ret)
        else:
            print('Error: Need to specify --scripts as well')
            sys.exit(1)
    else:
        print('Not support yet')
