import os
import shutil
import sys
import tarfile
from pathlib import Path

from flask import Flask, send_from_directory
from flask_restplus import Resource

from ..config import get_config
from ..util.dto import ScriptDto

api = ScriptDto.api

TARBALL_TEMP = Path('temp')
SCRIPT_ROOT = Path(get_config().SCRIPT_ROOT)

def make_tarfile(output_filename, source_dir):
    if output_filename[-2:] != 'gz':
        output_filename = output_filename + '.tar.gz'
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))

    return output_filename

def pack_script(test_suite):
    if not os.path.exists(SCRIPT_ROOT / (test_suite + '.py')):
        print("file {}.py does not exist".format(SCRIPT_ROOT / (test_suite)))
        return None

    output = str(TARBALL_TEMP / test_suite)
    try:
        if (os.path.exists(TARBALL_TEMP)):
            shutil.rmtree(TARBALL_TEMP)
        tmp_dir = TARBALL_TEMP / 'files'
        shutil.copytree(SCRIPT_ROOT, tmp_dir)
        output = make_tarfile(output, tmp_dir)
    except:
        print('making tar ball went wrong: {}'.format(sys.exc_info()))
        return None
    else:
        return output

@api.route('/<test_suite>')
@api.param('test_suite', 'bundled test suite script and dependencies')
@api.response(404, 'Script not found.')
class ScriptDownload(Resource):
    def get(self, test_suite):
        if test_suite.endswith('.py'):
            test_suite = test_suite[0:-3]

        tarball = pack_script(test_suite)
        if not tarball:
            api.abort(404)
        else:
            tarball = os.path.basename(tarball)
            return send_from_directory(Path(os.getcwd()) / TARBALL_TEMP, tarball)
