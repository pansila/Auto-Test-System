import argparse
import os
import sys
import time
import subprocess
from pathlib import Path
from shutil import copyfile

import pexpect
import requests

from ruamel import yaml

if os.name == 'nt':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Windows'
    keys_path = easy_rsa_path / 'keys'
    local_keys_path = Path('data') / 'keys'
    line_begin = ''
    line_end = os.linesep * 2
elif os.name == 'posix':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Linux'
    keys_path = easy_rsa_path / 'keys'
    local_keys_path = Path('data') / 'keys'
    line_begin = './'
    line_end = os.linesep
else:
    print('Unsupported platform')
    sys.exit(1)


def get_pexpect_child():
    if os.name == 'nt':
        from pexpect import popen_spawn

        shell = 'cmd.exe'
        child = popen_spawn.PopenSpawn(shell)
        child.expect('>')
        child.sendline('chcp 65001')
        child.expect(line_end)
    elif os.name == 'posix':
        shell = '/bin/bash'
        child = pexpect.spawn(shell)

    return child

def build_req(cert_name, comm_name):
    child = get_pexpect_child()
    child.sendline('cd {}'.format(easy_rsa_path))
    child.expect(line_end)

    if os.name == 'nt':
        child.sendline(line_begin + 'init-config')
        child.expect('copied.' + line_end)
    # elif os.name == 'posix':
    #     child.sendline('find -not -name "*.cnf" -not -type d -exec chmod +x \{\} \\;')
    #     child.expect(line_end)

    if os.name == 'nt':
        child.sendline(line_begin + 'vars')
    elif os.name == 'posix':
        child.sendline('source vars')
    child.expect(line_end)

    child.sendline(line_begin + 'clean-all')
    child.expect(line_end)

    time.sleep(1)

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

    time.sleep(1)        # to allow for .csr generating

    print('building csr completed')

def certificate_signing_request(url, cert_name):
    files = {'file': open(keys_path / (cert_name + '.csr'), 'rb')}
    r = requests.post(url, files=files)
    if r.status_code != 200:
        print('CSR failed: ' + r.text)
        return

    if r.content:
        with open(keys_path / (cert_name + '.crt'), 'wb') as ff:
            ff.write(r.content)
    else:
        print('CSR error')

def start_vpn():
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\\OpenVPN") as key:
            value, type = winreg.QueryValueEx(key, '')
            os.environ['PATH'] += ';' + value + '\\bin'
            subprocess.run(['openvpn.exe', 'data\\Windows\\client.ovpn'], check=True)
    elif os.name == 'posix':
        subprocess.run(['openvpn', 'data/Linux/client.conf'], check=True)

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

    if force_to_build or not os.path.exists(str(keys_path / 'mycert1.key')):
        build_req('mycert1', 'client11')

    if force_to_build or not os.path.exists(str(keys_path / 'mycert1.crt')):
        certificate_signing_request(g_config['server_url'] + ':' + str(g_config['server_port']) + '/cert/csr', 'mycert1')

        if not os.path.exists(str(keys_path / 'mycert1.crt')):
            print('Certificate signing failed')
            sys.exit(1)
        else:
            print('Certificate signing succeeded')

    if force_to_build or not os.path.exists(str(local_keys_path / 'mycert1.crt')):
        print('Copying keys to the configuration folder')
        copyfile(keys_path / 'mycert1.crt', local_keys_path / 'mycert1.crt')
        copyfile(keys_path / 'ca.crt', local_keys_path / 'ca.crt')
        copyfile(keys_path / 'mycert1.key', local_keys_path / 'mycert1.key')

    start_vpn()
