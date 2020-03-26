import os, sys
import requests
import argparse


def run(server, test, firmware, endpoints, tester, variables, testcases):
    payload = {}
    resource_id = None
    if firmware:
        with open(firmware, 'rb') as f:
            ret = requests.post('http://192.168.12.51:5000/taskresource/', data={'name': 'firmware.bin'}, files={'resource': f})
            if ret.status_code == 200:
                if ret.json()['status'] == 0:
                    resource_id = ret.json()['data']
                else:
                    return False
            else:
                return False

    payload['test_suite'] = test
    payload['endpoint_list'] = endpoints
    payload['upload_dir'] = resource_id
    payload['tester'] = tester
    if variables:
        payload['variables'] = variables
    if testcases:
        payload['testcases'] = testcases
    
    ret = requests.post('{}/task/'.format(server), json=payload)
    if ret.status_code != 200:
        return False

    print('Scheduled the test {} successfully'.format(test))
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('server', type=str)
    parser.add_argument('testsuite', type=str)
    parser.add_argument('-f', '--file', type=str)
    parser.add_argument('-p', '--tester', type=str)
    parser.add_argument('-e', '--endpoint', type=str, action='append', required=True)
    parser.add_argument('-v', '--variable', type=str, action='append', nargs=2, metavar=('name','value'))
    parser.add_argument('-t', '--testcase', type=str, action='append')
    args = parser.parse_args()

    if args.server[-1] == '/':
        args.server = args.server[0:-1]

    variables = {}
    if args.variable:
        for v in args.variable:
            variables[v[0]] = v[1]

    if run(args.server, args.testsuite, args.file, args.endpoint, args.tester, variables, args.testcase) == False:
        sys.exit(1)
    sys.exit(0)
