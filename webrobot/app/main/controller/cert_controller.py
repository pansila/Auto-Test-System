import os, sys
import pexpect
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

if os.name == 'nt':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Windows'
    keys_path = easy_rsa_path / 'keys'
    line_begin = ''
    line_end = os.linesep * 2
elif os.name == 'posix':
    easy_rsa_path = Path('..') / 'easy-rsa' / 'Linux'
    keys_path = easy_rsa_path / 'keys'
    line_begin = './'
    line_end = os.linesep
else:
    print('Unsupported platform')
    sys.exit(1)

if not os.path.exists(keys_path / 'ca.key'):
    child = get_pexpect_child()
    child.sendline('cd {}'.format(easy_rsa_path))
    child.expect(line_end)

    if os.name == 'nt':
        child.sendline(line_begin + 'vars')
    elif os.name == 'posix':
        child.sendline('source vars')
    child.expect(line_end)

    child.sendline(line_begin + 'build-ca')
    child.expect(']:', timeout=300)  # Country Name
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

    child.expect(os.linesep)

# if not os.path.exists(keys_path / 'ta.key'):
#     child = get_pexpect_child()
#     child.sendline('cd {}'.format(easy_rsa_path))
#     child.expect(line_end)

#     if os.name == 'nt':
#         child.sendline(line_begin + 'vars')
#     elif os.name == 'posix':
#         child.sendline('source vars')
#     child.expect(line_end)

#     child.sendline(line_begin + 'build-ta')
#     child.expect(os.linesep)

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
                filename = keys_path / (temp_id + '.csr')
                # file.save(str(filename))
                file.save(str(filename))
                break

        if filename:
            child = get_pexpect_child()
            child.sendline('cd {}'.format(easy_rsa_path))
            child.expect(line_end)

            if os.name == 'nt':
                child.sendline(line_begin + 'vars')
            elif os.name == 'posix':
                child.sendline('source vars')
            child.expect(line_end)

            if not os.path.exists(keys_path / 'ca.key'):
                return 'CA not found', 404

            cert_name = os.path.basename(filename).split('.')[0]
            child.sendline(line_begin + 'sign-req {}'.format(cert_name))
            child.expect(r'\[y/n\]:')
            child.sendline('y')

            try:
                child.expect('\[y/n\]', timeout=2)
            except pexpect.exceptions.TIMEOUT:
                return 'Signing certificate failed possibly due to repeated CSR requests', 404
            child.sendline('y')

            child.expect(line_end)

            return send_from_directory(Path(os.getcwd()) / os.path.dirname(filename), cert_name + '.crt')
        return 'CSR request is invalid', 404
