import sys
from importlib import import_module

sys.path.append('app')

def run():
	import_module('app').run()

if __name__ == '__main__':
	run()
