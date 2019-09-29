import os, sys
import pexpect
from pathlib import Path

def build_req(cert_name, comm_name):
	if os.name == 'nt':
		from pexpect import popen_spawn
		easy_rsa_path = Path('easy-rsa') / 'Windows'
		shell = 'cmd.exe'
		child = popen_spawn.PopenSpawn(shell)
		child.expect('>')
		child.sendline('chcp 65001')
		child.expect('\r\n\r\n')
	elif os.name == 'posix':
		easy_rsa_path = Path('easy-rsa') / 'Linux'
		shell = '/bin/bash'
		child = pexpect.spawn(shell)

	child.sendline('cd {}'.format(easy_rsa_path))
	child.expect('\r\n\r\n')

	child.sendline('init-config')
	child.expect('copied.\r\n\r\n')

	child.sendline('vars')
	child.expect('\r\n\r\n')

	child.sendline('clean-all')
	child.expect('\r\n\r\n')

	child.sendline('build-req {}'.format(cert_name))
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