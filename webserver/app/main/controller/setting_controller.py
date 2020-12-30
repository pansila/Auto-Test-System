import aiofiles
import os
from urllib.parse import urlparse
from pathlib import Path

from sanic import Blueprint
from sanic.log import logger
from sanic.views import HTTPMethodView
from sanic.response import json, file
from sanic_openapi import doc

from ..util import async_exists
from ..util.dto import SettingDto, json_response
from ..util.response import *


bp = Blueprint('setting', url_prefix='/setting')

@bp.get('/download')
@doc.summary('Get installation packages for the endpooint')
@doc.consumes(doc.String(name='file', description='The file path'))
@doc.produces(201, doc.File())
@doc.produces(200, json_response)
async def handler(request):
    download_file = request.args.get('file', default=None)
    if not download_file:
        return json(response_message(EINVAL, 'Field file is required'))

    ret = urlparse(request.url)
    if download_file == 'get-endpoint.py' or download_file == 'get-poetry.py':
        src = os.path.join('static', 'download', 'template.' + download_file)
        new = os.path.join('static', 'download', download_file)
        if await async_exists(new):
            await aiofiles.os.remove(new)
        async with aiofiles.open(src) as f_src, aiofiles.open(new, 'w') as f_new:
            async for line in f_src:
                if '{server_url}' in line:
                    server_url = ret.scheme + '://' + ret.netloc.replace('localhost', '127.0.0.1')
                    line = line.format(server_url=server_url)
                await f_new.write(line)
    return await file(os.path.join('static', 'download', download_file), status=201)

@bp.get('/get-endpoint/json')
@doc.summary('Get package information for the poetry')
@doc.produces(doc.String(name='releases', description='the release versions'))
def handler(request):
    return json({'releases': ["0.2.7"]})

@bp.get('/get-poetry/json')
@doc.summary('Get package information for the poetry')
@doc.produces(doc.String(name='releases', description='the release versions'))
def handler(request):
    return json({'releases': ["1.1.4"]})
