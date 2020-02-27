import os, sys
import pexpect
import threading
import time
import subprocess
from bson.objectid import ObjectId
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource

from app.main.model.database import *
from ..util.dto import CertDto
from ..util.errors import *
from ..config import get_config

api = CertDto.api
cert_key = CertDto.cert_key

UPLOAD_DIR = Path(get_config().UPLOAD_ROOT)

if os.name == 'nt':
    EASY_RSA_PATH = Path('..') / 'easy-rsa' / 'Windows'
    KEYS_PATH = EASY_RSA_PATH / 'keys'
    LINE_BEGIN = ''
    LINE_END = os.linesep * 2
elif os.name == 'posix':
    EASY_RSA_PATH = Path('..') / 'easy-rsa' / 'Linux'
    KEYS_PATH = EASY_RSA_PATH / 'keys'
    LINE_BEGIN = './'
    LINE_END = os.linesep
else:
    print('Unsupported platform')
    sys.exit(1)

def is_file_valid(file):
    return os.path.exists(file) and os.path.getsize(file) > 0

def get_pexpect_child():
    if os.name == 'nt':
        from pexpect import popen_spawn

        shell = 'cmd.exe'
        child = popen_spawn.PopenSpawn(shell)
        child.expect('>')
        child.sendline('chcp 65001')
        child.expect(LINE_END)
    elif os.name == 'posix':
        shell = '/bin/bash'
        child = pexpect.spawn(shell)
    #child.logfile = sys.stdout.buffer

    return child

class build_keys(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        if not is_file_valid(KEYS_PATH / 'ca.key') or not is_file_valid(KEYS_PATH / 'ca.crt'):
            print('Start to build CA key')
            start = time.time()
            child = get_pexpect_child()
            child.sendline('cd {}'.format(EASY_RSA_PATH))
            child.expect(LINE_END)

            if os.name == 'nt':
                child.sendline(LINE_BEGIN + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(LINE_END)

            child.sendline(LINE_BEGIN + 'build-ca')
            child.expect(']:', timeout=30)  # Country Name
            child.send('\n')

            child.expect(']:')  # State or Province Name
            child.sendline()

            child.expect(']:')  # Locality Name
            child.sendline()

            child.expect(']:')  # Organization Name
            child.sendline()

            child.expect(']:')  # Organizational Unit Name
            child.sendline()

            child.expect(']:')  # Common Name
            child.sendline('OpenVPN-CA')

            child.expect(']:')  # Name
            child.sendline()

            child.expect(']:')  # Email Address
            child.sendline()
            child.expect(os.linesep, timeout=30)  # only one line feed works on Windows

            time.sleep(1)
            child.kill(9)

            if is_file_valid(KEYS_PATH / 'ca.key') and is_file_valid(KEYS_PATH / 'ca.crt'):
                print('Succeeded to build CA key, time consumed: {}'.format(time.time() - start))
            else:
                print('Failed to build CA key')

        if not is_file_valid(KEYS_PATH / 'ta.key') and os.name == 'nt':
            print('Start to build TA key')
            start = time.time()
            child = get_pexpect_child()
            child.sendline('cd {}'.format(EASY_RSA_PATH))
            child.expect(LINE_END)

            if os.name == 'nt':
                child.sendline(LINE_BEGIN + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(LINE_END)

            child.sendline(LINE_BEGIN + 'build-ta')
            child.expect(LINE_END, timeout=30)

            time.sleep(1)
            child.kill(9)

            if is_file_valid(KEYS_PATH / 'ta.key'):
                print('Succeeded to build TA key, time consumed: {}'.format(time.time() - start))
            else:
                print('Failed to build TA key')

        if not is_file_valid(KEYS_PATH / 'server.key') or not is_file_valid(KEYS_PATH / 'server.crt'):
            print('Start to build server key')
            start = time.time()
            child = get_pexpect_child()
            child.sendline('cd {}'.format(EASY_RSA_PATH))
            child.expect(LINE_END)

            if os.name == 'nt':
                child.sendline(LINE_BEGIN + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(LINE_END)

            child.sendline(LINE_BEGIN + 'build-key-server server')
            child.expect(']:', timeout=30)  # Country Name
            child.send('\n')

            child.expect(']:')  # State or Province Name
            child.sendline()

            child.expect(']:')  # Locality Name
            child.sendline()

            child.expect(']:')  # Organization Name
            child.sendline()

            child.expect(']:')  # Organizational Unit Name
            child.sendline()

            child.expect(']:')  # Common Name
            child.sendline('server')

            child.expect(']:')  # Name
            child.sendline()

            child.expect(']:')  # Email Address
            child.sendline()

            child.expect(']:')  # A challenge password
            child.send('\n')    # don't know why only '\n' works

            child.expect(']:')  # An optional company name
            child.sendline()

            child.expect(r'\[y/n\]:')
            child.sendline('y')

            try:
                child.expect('\[y/n\]', timeout=2)
            except pexpect.exceptions.TIMEOUT:
                print('Signing certificate failed possibly due to repeated CSR requests')
            child.sendline('y')

            child.expect(LINE_END, timeout=30)

            time.sleep(1)
            child.kill(9)

            if is_file_valid(KEYS_PATH / 'server.key') and is_file_valid(KEYS_PATH / 'server.crt'):
                print('Succeeded to build server key, time consumed: {}'.format(time.time() - start))
            else:
                print('Failed to build server key')

        if not is_file_valid(KEYS_PATH / 'dh2048.pem'):
            print('Start to build DH key')
            start = time.time()
            child = get_pexpect_child()
            child.sendline('cd {}'.format(EASY_RSA_PATH))
            child.expect(LINE_END)

            if os.name == 'nt':
                child.sendline(LINE_BEGIN + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(LINE_END)

            child.sendline(LINE_BEGIN + 'build-dh')
            child.expect(r'[\.\+\*]{3}' + LINE_END, timeout=2000)

            time.sleep(1)
            child.kill(9)

            if is_file_valid(KEYS_PATH / 'dh2048.pem'):
                print('Succeeded to build DH key, time consumed: {}'.format(time.time() - start))
            else:
                print('Failed to build DH key')

if not 'thread' in globals():
    thread = build_keys()
    thread.daemon = True
    thread.start()

@api.route('/csr')
class certificate_signing_request(Resource):
    @api.doc('certificate signing request')
    def post(self):
        """
        Certificate signing request
        """
        filename = None
        for name, file in request.files.items():
            if file.filename.endswith('.csr'):
                temp_id = str(ObjectId())
                filename = KEYS_PATH / (temp_id + '.csr')
                # file.save(str(filename))
                file.save(str(filename))
                break

        if filename:
            child = get_pexpect_child()
            child.sendline('cd {}'.format(EASY_RSA_PATH))
            child.expect(LINE_END)

            if os.name == 'nt':
                child.sendline(LINE_BEGIN + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(LINE_END)

            if not is_file_valid(KEYS_PATH / 'ca.key'):
                return 'CA not found', 404

            cert_name = os.path.basename(filename).split('.')[0]
            child.sendline(LINE_BEGIN + 'sign-req {}'.format(cert_name))
            child.expect(r'\[y/n\]:')
            child.sendline('y')

            try:
                child.expect('\[y/n\]', timeout=2)
            except pexpect.exceptions.TIMEOUT:
                return 'Signing certificate failed possibly due to repeated CSR requests', 404
            child.sendline('y')

            child.expect(LINE_END)

            return send_from_directory(Path(os.getcwd()) / os.path.dirname(filename), cert_name + '.crt')
        return 'CSR request is invalid', 404

@api.route('/ca')
class certificate_authority_request(Resource):
    @api.doc('certificate authority request')
    def get(self):
        """
        Certificate authority request
        """
        if not is_file_valid(KEYS_PATH / 'ca.key'):
            return 'CA not found', 404

        return send_from_directory(Path(os.getcwd()) / KEYS_PATH, 'ca.crt')
