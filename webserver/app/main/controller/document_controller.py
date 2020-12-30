import aiofiles
import asyncio
import base64
import json
import datetime
import subprocess
import os
import shutil
from pathlib import Path

from sanic_openapi import doc
from sanic.response import json, file
from sanic import Blueprint
from sanic.views import HTTPMethodView
from async_files.utils import async_wraps

from ..model.database import Documentation, User
from ..util.dto import DocDto, json_response
from ..util.tarball import path_to_dict
from ..util.response import response_message, ENOENT, EINVAL, SUCCESS, EACCES, EPERM, EEXIST, GIT_ERROR
from ..util.decorator import token_required, organization_team_required_by_json, organization_team_required_by_args, organization_team_required_by_form
from ..util.get_path import get_document_root, get_pictures_root, is_path_secure
from ..util import js2python_bool, async_listdir, async_exists, async_rmtree, async_makedirs

_doc_roots = DocDto.doc_roots
_doc_history = DocDto.doc_history
_doc_pictures = DocDto.doc_pictures
_doc_content = DocDto.doc_content
_doc_query = DocDto.doc_query

bp = Blueprint('doc', url_prefix='/doc')

def check_editable(doc, user, organization, team, proprietary=None):
    if user.is_admin():
        return True
    if doc:  # modify a file
        if doc.proprietary:
            if doc.locked:
                if team:
                    for u in team.editors:
                        if u == user:
                            return True
                for u in organization.editors:
                    if u == user:
                        return True
            else:
                return True
        else:
            if doc.locked:
                if user.is_collaborator():
                    return True
            else:
                return True
    else:   # new a file
        if team:
            for u in team.editors:
                if u == user:
                    return True
        for u in organization.editors:
            if u == user:
                return True
        if not proprietary and user.is_collaborator():
            return True
    return False

@async_wraps
def git_checkout_add_push(repo_root, language, new_branch=False, debug=False):
    if new_branch:
        try:
            subprocess.run(['git', 'checkout', '-b', language], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
        except subprocess.CalledProcessError:
            return json(response_message(GIT_ERROR, "git checkout branch error"))

    with open(repo_root / '.revision') as f:
        revision = f.read()

    with open(repo_root / '.revision', 'w') as f:
        f.write(str(int(revision) + 1))

    try:
        subprocess.run(['git', 'add', '.'], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return json(response_message(GIT_ERROR, "git add error"))

    try:
        subprocess.run(['git', 'commit', '-m', str(int(revision) + 1)], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return json(response_message(GIT_ERROR, "git commit error"))

    try:
        subprocess.run(['git', 'push', 'origin', language], cwd=repo_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return json(response_message(GIT_ERROR, "git push error"))

    return json(response_message(SUCCESS))

@bp.get('/roots')
@doc.summary('Return document paths in the root directory')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(doc.Boolean(name='proprietary'))
@doc.consumes(doc.String(name='language'))
@doc.produces(_doc_roots)
@token_required
@organization_team_required_by_args
async def handler(self, request):
    organization = request.ctx.organization
    team = request.ctx.team
    proprietary = js2python_bool(request.args.get('proprietary', False))
    language = request.args.get('language', 'en')

    paths = [{'value': 0, 'label': '/'}]
    if proprietary:
        doc_root = get_document_root(language, organization, team)
    else:
        doc_root = get_document_root(language, None, None)
    dirs = await async_listdir(doc_root)
    for i, d in enumerate(dirs):
        if (doc_root / d).is_dir():
            paths.append({'value': i + 1, 'label': d})
    return json(response_message(SUCCESS, paths=paths))

@bp.get('/check')
@doc.summary('Check whether the requester has the privilege to edit the page')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_doc_query)
@doc.produces(json_response)
@token_required
@organization_team_required_by_args
async def handler(self, request):
    path = request.args.get('path', None)
    if not path:
        return json(response_message(EINVAL))
    language = request.args.get('language', 'en')
    proprietary = js2python_bool(request.args.get('proprietary', False))

    organization = request.ctx.organization
    team = request.ctx.team
    user = request.ctx.get('user')

    query = {'path': path, 'proprietary': proprietary, 'language': language}
    if proprietary:
        query['organization'] = organization
        if team:
            query['team'] = team
    doc = await Documentation.find_one(query)
    # if not doc:
    #     return json(response_message(ENOENT))
    
    if check_editable(doc, user, organization, team):
        return json(response_message(SUCCESS))
    return json(response_message(EACCES))

@bp.get('/history')
@doc.summary('get the page change history')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.consumes(_doc_query)
@doc.produces(_doc_history)
@token_required
@organization_team_required_by_args
async def handler(self, request):
    language = request.args.get('language', 'en')
    proprietary = js2python_bool(request.args.get('proprietary', False))
    path = request.args.get('path', None)
    if not path:
        return json(response_message(ENOENT))

    organization = request.ctx.organization
    team = request.ctx.team
    user = request.ctx.user

    query = {'path': path, 'proprietary': proprietary, 'language': language}
    if proprietary:
        query['organization'] = organization
        if team:
            query['team'] = team
    doc = await Documentation.find_one(query)
    if not doc:
        return json(response_message(ENOENT))
    
    if proprietary:
        doc_root = get_document_root(language, organization, team)
    else:
        doc_root = get_document_root(language, None, None)
    doc_root_parent = doc_root.parent

    process = await asyncio.create_subprocess_exec('git', 'checkout', language, cwd=doc_root_parent, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await process.wait()
    if process.returncode != 0:
        return json(response_message(GIT_ERROR, 'git checkout error'))

    process = await asyncio.create_subprocess_exec('git', 'log', '--pretty=oneline', '-p', Path(language) / doc.path, '-10', cwd=doc_root_parent, stdout=asyncio.subprocess.PIPE)

    history = []
    results = []
    pre_line = None
    cnt = 0
    revision = None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        line = line.decode()
        parts = line.split(' ')
        if parts[0] == 'diff':
            if revision is not None:
                history.append({'title': revision, 'revision': revision, 'description': '\n'.join(results[5:-1])})
            cid, revision = pre_line.split(' ')
            results = []
            cnt = 0
        if '.md ' in line or 0 < cnt < 10:
            cnt += 1
            if line != '\\ No newline at end of file':
                results.append(line)
        pre_line = line
    else:
        history.append({'title': revision, 'revision': revision, 'description': '\n'.join(results[5:])})

    return json(response_message(SUCCESS, history=history))

class PicturePathView(HTTPMethodView):
    @doc.summary('Return the directories of the current path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query)
    @doc.produces(_doc_roots)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')
        path = request.args.get('path', None)
        if not path:
            return json(response_message(EINVAL, 'field path can not be empty'))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))

        if path.suffix:
            path = path.parent

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)
        pic_root_parent = pic_root.parent

        for f in await async_listdir(pic_root_parent / path):
            if (pic_root_parent / path / f).is_dir():
                paths.append({'value': f, 'label': f})
        return json(response_message(SUCCESS, paths=paths))

    @doc.summary('Create a directory under the specified path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def post(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return json(response_message(EINVAL, 'field path can not be empty'))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))

        if path.suffix:
            path = path.parent

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)

        pic_root_parent = pic_root.parent
        if await async_exists(pic_root_parent / path):
            return json(response_message(EEXIST))
        await aiofiles.os.mkdir(pic_root_parent / path)

        return json(response_message(SUCCESS))

    @doc.summary('Delete a directory under the specified path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return json(response_message(EINVAL, 'field path can not be empty'))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))
        if path == '.' or path == './':
            return json(response_message(EPERM, 'root directory can not be deleted'))
        if path == language or path == './' + language or path == '.\\' + language:
            return json(response_message(EPERM, 'language directory can not be deleted'))

        if path.suffix:
            path = path.parent

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)

        pic_root_parent = pic_root.parent
        if not await async_exists(pic_root_parent / path):
            return json(response_message(ENOENT))
        await async_rmtree(pic_root_parent / path)

        return json(response_message(SUCCESS))

class DocumentPictureView(HTTPMethodView):
    @doc.summary('Return all pictures under a path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query)
    @doc.produces(_doc_pictures)
    @token_required
    @organization_team_required_by_args
    async def get(self, request):
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')
        path = request.args.get('path', None)
        if not path:
            return json(response_message(EINVAL))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))

        if path.suffix:
            path = path.parent

        if proprietary:
            organization = request.ctx.organization
            team = request.ctx.team
            if not organization and not team:
                return json(response_message(EINVAL))
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)
        pic_root_parent = pic_root.parent

        fileList = []
        for f in await async_listdir(pic_root_parent / path):
            fileName = pic_root_parent / path / f
            if fileName.is_dir():
                continue
            async with aiofiles.open(fileName, 'rb') as pic:
                data = await pic.read()
                fileList.append({
                    'name': f,
                    'data': base64.b64encode(data).decode('ascii'),
                    'type': f'image/{f.suffix[1:]}',
                    'size': os.path.getsize(fileName)
                })
        return json(response_message(SUCCESS, file_list=fileList))

    @doc.summary('Upload pictures to a path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_form
    async def post(self, request):
        proprietary = js2python_bool(request.form.get('proprietary', False))
        language = request.form.get('language', 'en')
        path = request.form.get('path', None)
        if not path:
            return json(response_message(EINVAL))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))

        if path.suffix:
            path = path.parent

        if proprietary:
            organization = request.ctx.organization
            team = request.ctx.team
            if not organization and not team:
                return json(response_message(EINVAL))
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)
        pic_root_parent = pic_root.parent

        for k in request.files:
            await async_wraps(request.files[k].save)(pic_root_parent / path / k)

        return json(response_message(SUCCESS))

    @doc.summary('Remove a picture under a path')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query, location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request):
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return json(response_message(EINVAL))
        path.lstrip('/').lstrip('\\')
        path = Path(path)
        if not is_path_secure(path):
            return json(response_message(EINVAL, 'Illegal path'))

        if path.suffix:
            path = path.parent

        if proprietary:
            organization = request.ctx.organization
            team = request.ctx.team
            if not organization and not team:
                return json(response_message(EINVAL))
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not await async_exists(pic_root):
            await aiofiles.os.mkdir(pic_root)
        pic_root_parent = pic_root.parent

        filename = request.json.get('filename', None)
        if not filename:
            return json(response_message(EINVAL))
        await aiofiles.os.remove(pic_root_parent / path / filename)

        return json(response_message(SUCCESS))

class DocumentView(HTTPMethodView):
    @doc.summary('Return markdown file content')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(doc.String(name='proprietary'), location='body')
    @doc.consumes(doc.String(name='language'), location='body')
    @doc.produces(_doc_content)
    @token_required
    @organization_team_required_by_args
    async def get(self, request, file_path):
        if not file_path:
            file_path = 'home.md'
        if file_path.endswith('/'):
            file_path = file_path[:-1]
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            if team:
                query['team'] = team
        doc = await Documentation.find_one(query)
        if not doc:
            return json(response_message(ENOENT))
        doc.view_times += 1
        await doc.commit()
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        doc_root_parent = doc_root.parent

        process = await asyncio.create_subprocess_exec('git', 'checkout', language, cwd=doc_root_parent, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()
        if process.returncode != 0:
            return json(response_message(GIT_ERROR, 'git checkout error'))

        async with aiofiles.open((doc_root / doc.path).resolve()) as f:
            return json(response_message(SUCCESS, content=await f.read(), locked=doc.locked))

    @doc.summary('Update a markdown file')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(doc.String(name='proprietary'), location='body')
    @doc.consumes(doc.String(name='language'), location='body')
    @doc.consumes(doc.String(name='doc_content'), location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def post(self, request, file_path):
        if not file_path:
            return json(response_message(EINVAL, 'file\'s path is required'))
        if not is_path_secure(file_path):
            return json(response_message(EINVAL, 'Illegal path'))

        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.json.get('proprietary', False))
        user = request.ctx.user
        doc_content = request.json.get('doc_content', '')
        language = request.json.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'filename': os.path.basename(file_path), 'language': language}
        if proprietary:
            query['organization'] = organization
            if team:
                query['team'] = team
        doc = await Documentation.find_one(query)
        if not doc:
            if not check_editable(None, user, organization, team, proprietary):
                return json(response_message(EACCES))
            doc = Documentation(**query)
            doc.uploader = user
        else:
            if not check_editable(doc, user, organization, team):
                return json(response_message(EACCES))
            doc.last_modified = datetime.datetime.utcnow()
            doc.last_modifier = user
        if file_path == 'home.md':
            doc.locked = True
        await doc.commit()

        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        if not doc_root.exists():
            await async_makedirs(doc_root)

        doc_root_parent = doc_root.parent
        git_root = doc_root_parent / 'doc.git'
        if not git_root.exists():
            await async_makedirs(git_root)
            process = await asyncio.create_subprocess_exec('git', '--bare', 'init', cwd=git_root)
            await process.wait()
            if process.returncode != 0:
                return json(response_message(GIT_ERROR, "git init error"))

        if not (doc_root_parent / '.git').exists():
            async with aiofiles.open(doc_root_parent / '.gitignore', 'w') as f:
                await f.write('doc.git\n')
            async with aiofiles.open(doc_root_parent / '.revision', 'w') as f:
                await f.write('0')
            process = await asyncio.create_subprocess_exec('git', 'init', cwd=doc_root_parent)
            await process.wait()
            if process.returncode != 0:
                return json(response_message(GIT_ERROR, "git local init error"))
            process = await asyncio.create_subprocess_exec('git', 'remote', 'add', 'origin', git_root.resolve(), cwd=doc_root_parent)
            await process.wait()
            if process.returncode != 0:
                return json(response_message(GIT_ERROR, "git remote add error"))

            await git_checkout_add_push(doc_root_parent, 'master', new_branch=True)

        process = await asyncio.create_subprocess_exec('git', 'checkout', language, cwd=doc_root_parent, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()
        if process.returncode != 0:
            process = await asyncio.create_subprocess_exec('git', 'checkout', '--orphan', language, cwd=doc_root_parent)
            await process.wait()
            if process.returncode != 0:
                return json(response_message(GIT_ERROR, "git checkout branch error"))
            else:
                for f in await async_listdir(doc_root_parent):
                    if f != 'doc.git' and f != '.git' and f != '.gitignore' and f != language:
                        try:
                            await aiofiles.os.remove(doc_root_parent / f)
                        except OSError:
                            await async_rmtree(doc_root_parent / f)
                async with aiofiles.open(doc_root_parent / '.revision', 'w') as f:
                    await f.write('0')

        dirname = os.path.dirname(doc.path)
        if dirname and not (doc_root / dirname).exists():
            await async_makedirs(doc_root / dirname)
        async with aiofiles.open(doc_root / doc.path, 'w') as f:
            await f.write(doc_content)

        await git_checkout_add_push(doc_root_parent, language)
        return json(response_message(SUCCESS))

    @doc.summary('Delete a markdown file')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(doc.String(name='proprietary'), location='body')
    @doc.consumes(doc.String(name='language'), location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def delete(self, request, file_path):
        if not file_path:
            return json(response_message(EINVAL, 'file\'s path is required'))
        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = request.ctx.organization
        team = request.ctx.team
        proprietary = js2python_bool(request.json.get('proprietary', False))
        user = request.ctx.user
        language = request.json.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            if team:
                query['team'] = team
        doc = await Documentation.find_one(query)
        if not doc:
            return json(response_message(ENOENT, 'document not found'))
        if not check_editable(doc, user, organization, team):
            return json(response_message(EACCES))
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        doc_root_parent = doc_root.parent

        process = await asyncio.create_subprocess_exec('git', 'checkout', language, cwd=doc_root_parent, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()
        if process.returncode != 0:
            return json(response_message(ENOENT, 'file not found'))

        await aiofiles.os.remove(doc_root / doc.path)
        await doc.delete()

        await git_checkout_add_push(doc_root_parent, language)

        return json(response_message(SUCCESS))

    @doc.summary('Lock a document file so that only allowed users can edit it')
    @doc.consumes(doc.String(name='X-Token'), location='header')
    @doc.consumes(_doc_query, location='body')
    @doc.consumes(doc.String(name='lock'), location='body')
    @doc.consumes(doc.String(name='proprietary'), location='body')
    @doc.consumes(doc.String(name='language'), location='body')
    @doc.produces(json_response)
    @token_required
    @organization_team_required_by_json
    async def patch(self, request, file_path):
        if not file_path:
            return json(response_message(EINVAL, 'file\'s path is required'))
        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = request.ctx.organization
        team = request.ctx.team
        user = request.ctx.user
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        lock = js2python_bool(request.json.get('lock', None))

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            if team:
                query['team'] = team
        doc = await Documentation.find_one(query)
        if not doc:
            return json(response_message(ENOENT, 'document not found'))
        if not check_editable(doc, user, organization, team):
            return json(response_message(EACCES))
        doc.locked = lock
        await doc.commit()
        return json(response_message(SUCCESS))

bp.add_route(DocumentPictureView.as_view(), '/pictures')
bp.add_route(PicturePathView.as_view(), '/picture/path')
bp.add_route(DocumentView.as_view(), '/<file_path:path>')
