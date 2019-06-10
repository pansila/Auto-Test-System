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
        print('Source files {} do not exist'.format(src))
        return None

    tmp_dir = dst / 'files'
    try:
        if (os.path.exists(tmp_dir)):
            shutil.rmtree(tmp_dir)
        shutil.copytree(src, tmp_dir)
        output = make_tarfile(output, tmp_dir)
    except Exception as e:
        print(e)
        return None
    else:
        return output

def path_to_dict(path):
    d = {'label': os.path.basename(path)}
    if os.path.isdir(path):
        d['type'] = "directory"
        d['children'] = [path_to_dict(os.path.join(path,x)) for x in os.listdir(path)]
    else:
        d['type'] = "file"
    return d
