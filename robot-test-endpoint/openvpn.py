import os, sys
import pexpect
import requests
from pathlib import Path
from ruamel import yaml
import argparse

if os.name == 'nt':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Windows'
    keys_path = easy_rsa_path / 'keys'
elif os.name == 'posix':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Linux'
    keys_path = easy_rsa_path / 'keys'
else:
    print('Unsupported platform')
    sys.exit(1)

def build_req(cert_name, comm_name):
    if os.name == 'nt':
        from pexpect import popen_spawn

        line_begin = ''
        line_end = os.linesep * 2
        shell = 'cmd.exe'
        child = popen_spawn.PopenSpawn(shell)
        child.expect('>')
        child.sendline('chcp 65001')
        child.expect(line_end)
    elif os.name == 'posix':
        line_begin = './'
        line_end = os.linesep
        shell = '/bin/bash'
        child = pexpect.spawn(shell)

    child.sendline('cd {}'.format(easy_rsa_path))
    child.expect(line_end)

    if os.name == 'nt':
        child.sendline(line_begin + 'init-config')
        child.expect('copied.' + line_end)
    elif os.name == 'posix':
        child.sendline('find -not -name "*.cnf" -not -type d -exec chmod +x \{\} \\;')
        child.expect(line_end)

    if os.name == 'nt':
        child.sendline(line_begin + 'vars')
    elif os.name == 'posix':
        child.sendline('source vars')
    child.expect(line_end)

    child.sendline(line_begin + 'clean-all')
    child.expect(line_end)

    child.sendline(line_begin + 'build-req {}'.format(cert_name))
    child.expect(']:')  # Country Name
    child.send('\n')    # don't know why only '\n' works

    child.expect(']:')  # State or Province Name
    child.sendline()

    child.expect(']:')  # Locality Name
    child.sendline()

    child.expect(']:')  # Organization Name
    child.sendline()

    child.expect(']:')  # Organizational Unit Name
    child.sendline()

    child.expect(']:')  # Common Name
    child.sendline(comm_name)
    # print(child.before.decode('cp936'))
    # print(child.after.decode('cp936'))

    child.expect(']:')  # Name
    child.sendline()

    child.expect(']:')  # Email Address
    child.sendline()

    child.expect(']:')  # A challenge password
    child.send('\n')    # don't know why only '\n' works

    child.expect(']:')  # An optional company name
    child.sendline()

    child.expect(os.linesep)

    print('building csr completed')

def certificate_signing_request(url, cert_name):
    files = {'file': open(keys_path / (cert_name + '.csr'), 'rb')}
    r = requests.post(url, files=files)
    if r.status_code != 200:
        print('CSR failed')
        return

    if r.content:
        with open(keys_path / (cert_name + '.crt'), 'wb') as ff:
            ff.write(r.content)
    else:
        print('CSR error')

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', '-f', type=str2bool, nargs='?', const=True, default=False,
                        help='force to build key and certificate')
    args = parser.parse_args()

    force_to_build = args.force

    g_config = None
    with open('config.yml', 'r', encoding='utf-8') as f:
        g_config = yaml.load(f, Loader=yaml.RoundTripLoader)

    if force_to_build or not os.path.exists(keys_path / 'mycert1.key'):
        build_req('mycert1', 'client11')

    if force_to_build or not os.path.exists(keys_path / 'mycert1.crt'): 
        certificate_signing_request(g_config['server_url'] + ':' + str(g_config['server_port']) + '/cert/csr', 'mycert1')
