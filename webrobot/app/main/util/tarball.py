import os
import sys
import shutil
import tarfile
from pathlib import Path

def make_tarfile(output_filename, source_dir):
    if output_filename[-2:] != 'gz':
        output_filename = output_filename + '.tar.gz'
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))

    return output_filename

def pack_files(filename, src, dst):
    if not isinstance(dst, Path):
        dst = Path(dst)

    output = str(dst / filename)

    if not os.path.exists(src):
        return None

    try:
        if (os.path.exists(dst)):
            shutil.rmtree(dst)
        tmp_dir = dst / 'files'
        shutil.copytree(src, tmp_dir)
        output = make_tarfile(output, tmp_dir)
    except:
        print('making tar ball went wrong: {}'.format(sys.exc_info()))
        return None
    else:
        return output
