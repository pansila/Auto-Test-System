import sys
import unittest
from importlib import import_module

sys.path.append('app')

def run():
	import_module('app').run()

def test():
    tests = unittest.TestLoader().discover('app/test', pattern='test*.py')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if result.wasSuccessful():
        return 0
    return 1

if __name__ == '__main__':
	run()
