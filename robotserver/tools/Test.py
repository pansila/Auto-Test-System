import mistune
import os, sys
from os import path
import datetime
from mongoengine import *
import argparse

sys.path.append('robot_python_scripts')
from customtestlibs.database_client import Test

def strip_char(item):
    item = item.strip()
    if item.startswith('${'):
        item = item[2:]
    if item.endswith('}'):
        item = item[0:-1]
    return item

def update_test(scripts_dir):
    for root, _, files in os.walk(scripts_dir):
        for md_file in files:
            if not md_file.endswith('.md'):
                continue

            test_suite = md_file.split('.')[0]
            old_test = Test.objects(test_suite=test_suite)
            test = Test()
            test.test_suite = test_suite
            test.author = 'John'
            test.test_cases = []

            md_file = path.join(root, md_file)
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
                                if not c[0] == '---':
                                    test.parameters[strip_char(c[0])] = strip_char(c[1])
            if len(old_test) == 0:
                test.create_date = datetime.datetime.utcnow()
                test.save()
                print('Found new test suite {}, added to database'.format(test_suite))
            elif len(old_test) != 1:
                print('Found duplicate named test suite in the datebase: {}!!!'.format(test_suite))
                return
            elif old_test[0] != test:
                print('Update test suite {}'.format(test_suite))
                test.create_date = old_test[0].create_date
                test.update_date = datetime.datetime.utcnow()
                old_test[0].delete()
                test.save()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', type=str, required=True,
                    help='specify an action to run',
                    choices=['CREATE', 'READ', 'UPDATE', 'DELETE'])
    parser.add_argument('--script_folder', type=str,
                    help='specify the root folder of robot scripts, required if action=UPDATE')
    args = parser.parse_args()

    connect('autotest')

    if args.action == 'READ':
        print(Test.get_list())
    elif args.action == 'UPDATE':
        if args.script_folder:
            update_test(args.script_folder)
        else:
            print('Need to specify --script_folder')
