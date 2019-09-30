import os, sys
import pexpect
import requests
from pathlib import Path
from ruamel import yaml

if os.name == 'nt':
    easy_rsa_path = Path('easy-rsa') / 'Windows'
    keys_path = easy_rsa_path / 'keys'
elif os.name == 'posix':
    easy_rsa_path = Path('easy-rsa') / 'Linux'
    keys_path = easy_rsa_path / 'keys'

CSR_URL = 'http://'

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
        easy_rsa_path = Path('easy-rsa') / 'Linux'
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

    child.sendline('\n')
    child.expect(']:')  # State or Province Name

    child.sendline('\n')
    child.expect(']:')  # Locality Name

    child.sendline('\n')
    child.expect(']:')  # Organization Name

    child.sendline('\n')
    child.expect(']:')  # Organizational Unit Name

    child.sendline('{}\n'.format(comm_name))
    child.expect(']:')  # Common Name
    # print(child.before.decode('cp936'))
    # print(child.after.decode('cp936'))

    child.sendline('\n')
    child.expect(']:')  # Name

    child.sendline('\n')
    child.expect(']:')  # Email Address

    child.sendline('\n')
    child.expect(']:')  # A challenge password

def certificate_signing_request(url):
    files = {'file': open(keys_path / 'mycert1.csr', 'rb')}
    r = requests.post(url, files=files)
    if r.status_code == 404:
        print('CSR failed')
        return
    with open(keys_path / 'mycert1.crt', 'wb') as ff:
        ff.write(r.content)

if __name__ == '__main__':
    g_config = None
    with open('config.yml', 'r', encoding='utf-8') as f:
        g_config = yaml.load(f, Loader=yaml.RoundTripLoader)

    if not os.path.exists(keys_path / 'mycert1.key'):
        build_req('mycert1', 'client11')

    if not os.path.exists(keys_path / 'mycert1.crt'): 
        certificate_signing_request(g_config['server_url'] + ':' + g_config['server_port'] + '/csr')
