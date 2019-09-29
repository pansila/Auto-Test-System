import os, sys
import pexpect
from pathlib import Path

def build_req(cert_name, comm_name):
	if os.name == 'nt':
		from pexpect import popen_spawn

		line_begin = ''
		line_end = os.linesep * 2
		easy_rsa_path = Path('easy-rsa') / 'Windows'
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

if __name__ == '__main__':
	build_req('mycert1', 'client11')