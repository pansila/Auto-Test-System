import os, sys
import pexpect
import time
import subprocess
from bson.objectid import ObjectId
from pathlib import Path
from flask import request, send_from_directory
from flask_restx import Resource

from ..util.dto import CertDto
from ..util.response import *
from ..config import get_config

api = CertDto.api
cert_key = CertDto.cert_key

UPLOAD_DIR = Path(get_config().UPLOAD_ROOT)

if os.name == 'nt':
    EASY_RSA_PATH = Path('..') / 'tools' / 'easy-rsa' / 'Windows'
    KEYS_PATH = EASY_RSA_PATH / 'keys'
    LINE_BEGIN = ''
    LINE_END = os.linesep * 2
elif os.name == 'posix':
    EASY_RSA_PATH = Path('..') / 'tools' / 'easy-rsa' / 'Linux'
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
