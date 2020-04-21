import os
import sys
import shutil
import tarfile
import zipfile
from pathlib import Path
from flask import current_app

def make_tarfile_from_dir(output_filename, source_dir):
    if not output_filename.endswith('.gz'):
        output_filename += '.tar.gz'
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname='.')

    return output_filename

def make_tarfile(output_filename, files):
    if not output_filename.endswith('.gz'):
        output_filename += '.tar.gz'
    with tarfile.open(output_filename, "w:gz") as tar:
        for f in files:
            tar.add(f)

    return output_filename

def empty_folder(folder):
    for root, dirs, files in os.walk(folder):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))

def pack_files(filename, src, dst):
    output = os.path.join(dst, filename)

    if not os.path.exists(src):
        current_app.logger.error('Source files {} do not exist'.format(src))
        return None

    try:
        output = make_tarfile_from_dir(output, src)
    except Exception as e:
        current_app.logger.exception(e)
        return None
    else:
        return output

def path_to_dict(path):
    d = {'label': os.path.basename(path)}
    if os.path.isdir(path):
        d['type'] = "directory"
        d['children'] = sorted([path_to_dict(os.path.join(path,x)) for x in os.listdir(path)], key=lambda x: x['type'] == 'directory')
    else:
        d['type'] = "file"
    return d
