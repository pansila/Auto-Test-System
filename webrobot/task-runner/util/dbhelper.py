import mistune
import os, sys
from os import path
import datetime
from mongoengine import *
import argparse

sys.path.append('.')
from app.main.model.database import Test
from app.main.config import get_config

def filter_kw(item):
    item = item.strip()
    if item.startswith('${'):
        item = item[2:]
        if not item.endswith('}'):
            print('{ } mismatch for ' + item)
        else:
            item = item[0:-1]
    return item

def update_test(scripts_dir):
    test_suites = []
    for root, _, files in os.walk(scripts_dir):
        for md_file in files:
            if not md_file.endswith('.md'):
                continue

            test_suite = md_file.split('.')[0]
            test = Test()
            test.test_suite = test_suite
            test.author = 'John'
            test.test_cases = []

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
                            for c in t["cells"]:
                                if not c[0] == '---' and not c[0].startswith('#') and \
                                        not c[0] == '...' and not c[0].startswith('@'):
                                    test.variables[filter_kw(c[0])] = filter_kw(c[1])
            try:
                old_test = Test.objects(test_suite=test_suite).get()
            except Test.DoesNotExist:
                test.create_date = datetime.datetime.utcnow()
                test.save()
                print('Added new test suite {} to database'.format(test_suite))
                continue
            except Test.MultipleObjectsReturned:
                test_suites.pop()
                print('Found duplicate test suite in the datebase: {}, abort'.format(test_suite))
                return 1

            if old_test != test:
                print('Update test suite {}'.format(test_suite))
                test.create_date = old_test.create_date
                test.update_date = datetime.datetime.utcnow()
                old_test.delete()
                test.save()

    # clean up stale test suites
    for test_old in Test.objects({}):
        for test_new in test_suites:
            if test_new == test_old.test_suite:
                break
        else:
            Test.objects(pk=test_old.id).modify(remove=True)
            print('Remove stale test suite {}'.format(test_old.test_suite))

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
            ret = update_test(args.scripts)
            sys.exit(ret)
        else:
            print('Error: Need to specify --scripts as well')
            sys.exit(1)
    else:
        print('Not support yet')
