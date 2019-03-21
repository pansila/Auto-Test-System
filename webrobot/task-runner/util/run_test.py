import os, sys
import requests
import argparse


def run(server, test, firmware, endpoints, tester, variables, testcases):
    payload = {}
    resource_id = None
    if firmware is not None:
        with open(firmware, 'rb') as f:
            ret = requests.post('http://192.168.12.51:5000/taskresource/', data={'name': 'firmware.bin'}, files={'resource': f})
            # print(ret.text)
            if ret.status_code == 200:
                if ret.json()['status'] == 0:
                    resource_id = ret.json()['data']
                else:
                    return False
            else:
                return False

    payload['endpoint_list'] = endpoints
    payload['upload_dir'] = resource_id
    payload['tester'] = tester
    if variables is not None:
        payload['variables'] = variables
    if testcases is not None:
        payload['testcases'] = testcases
    
    ret = requests.post('{}/task/{}'.format(server, test), json=payload)
    if ret.status_code != 200:
        return False

    # print(ret.text)
    print('Scheduled the test {} successfully'.format(test))
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('server', type=str)
    parser.add_argument('testsuite', type=str)
    parser.add_argument('endpoints', type=str)
    parser.add_argument('--file', type=str)
    parser.add_argument('--tester', type=str)
    parser.add_argument('-v', '--variable', type=str, action='append', nargs=2, metavar=('name','value'))
    parser.add_argument('-t', '--testcases', type=str)
    args = parser.parse_args()

    if args.server[-1] == '/':
        args.server = args.server[0:-1]

    endpoints = None
    if args.endpoints:
        endpoints = args.endpoints.split('#')
    testcases = None
    if args.testcases:
        testcases = args.testcases.split('#')
    variables = {}
    if args.variable:
        for v in args.variable:
            variables[v[0]] = v[1]

    # print(args.server, args.testsuite, args.firmware, args.endpoints, args.tester, variables, args.testcases)

    if run(args.server, args.testsuite, args.file, endpoints, args.tester, variables, testcases) == False:
        sys.exit(1)
    sys.exit(0)
