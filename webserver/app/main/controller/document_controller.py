import base64
import json
import datetime
import subprocess
import os
import shutil
from pathlib import Path
from flask import send_from_directory, current_app, render_template, make_response, request
from flask_restx import Resource

from ..model.database import Documentation, User
from ..util.dto import DocDto
from ..util.tarball import path_to_dict
from ..util.response import response_message, ENOENT, EINVAL, SUCCESS, EACCES, UNKNOWN_ERROR, EPERM, EEXIST
from ..util.decorator import token_required, organization_team_required_by_json, organization_team_required_by_args, organization_team_required_by_form
from ..util.get_path import get_document_root, get_pictures_root, is_path_secure
from ..util import js2python_bool

api = DocDto.api
_path = DocDto.path

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

def git_checkout_add_push(repo_root, language, new_branch=False, debug=False):
    if new_branch:
        try:
            subprocess.run(['git', 'checkout', '-b', language], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
        except subprocess.CalledProcessError:
            return response_message(UNKNOWN_ERROR, "git checkout branch error"), 500

    with open(repo_root / '.revision') as f:
        revision = f.read()

    with open(repo_root / '.revision', 'w') as f:
        f.write(str(int(revision) + 1))

    try:
        subprocess.run(['git', 'add', '.'], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return response_message(UNKNOWN_ERROR, "git add error"), 500

    try:
        subprocess.run(['git', 'commit', '-m', str(int(revision) + 1)], cwd=repo_root, check=True, stdout=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return response_message(UNKNOWN_ERROR, "git commit error"), 500

    try:
        subprocess.run(['git', 'push', 'origin', language], cwd=repo_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL if not debug else None)
    except subprocess.CalledProcessError:
        return response_message(UNKNOWN_ERROR, "git push error"), 500

    return response_message(SUCCESS)

@api.route('/roots')
class DocumentRoots(Resource):
    @api.doc('return document paths in the root directory')
    @token_required
    @organization_team_required_by_args
    @api.marshal_list_with(_path)
    def get(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')

        paths = [{'value': 0, 'label': '/'}]
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        for root, dirs, files in os.walk(doc_root):
            if not doc_root.match(root):
                continue
            for i, d in enumerate(dirs):
                paths.append({'value': i + 1, 'label': d})
        return paths

@api.route('/check')
class DocumentRoots(Resource):
    @api.doc('check whether the requester has the privilege to edit the page')
    @token_required
    @organization_team_required_by_args
    def get(self, **kwargs):
        user = kwargs.get('user')
        assert user is not None
        language = request.args.get('language', 'en')

        path = request.args.get('path', None)
        if not path:
            return response_message(ENOENT), 401
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))

        query = {'path': path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            return response_message(ENOENT)
        
        if check_editable(doc, user, organization, team):
            return response_message(SUCCESS)
        return response_message(EACCES)

@api.route('/history')
class DocumentRoots(Resource):
    @api.doc('get the page change history')
    @token_required
    @organization_team_required_by_args
    def get(self, **kwargs):
        user = kwargs.get('user')
        assert user is not None
        language = request.args.get('language', 'en')

        path = request.args.get('path', None)
        if not path:
            return response_message(ENOENT)
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))

        query = {'path': path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            return response_message(ENOENT)
        
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        doc_root_root = Path(os.path.dirname(doc_root))

        try:
            subprocess.run(['git', 'checkout', language], cwd=doc_root_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return response_message(ENOENT, 'file not found')

        try:
            commits = subprocess.check_output(['git', 'log', '--pretty=oneline', '-p', Path(language) / doc.path], cwd=doc_root_root, text=True)
        except subprocess.CalledProcessError:
            return response_message(ENOENT, 'git history error')

        history = []
        results = []
        pre_line = None
        cnt = 0
        revision = None
        for line in commits.splitlines():
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

        return response_message(SUCCESS, history=history)

@api.route('/picture/path')
class DocumentRoots(Resource):
    @api.doc('return the directories of the current path')
    @token_required
    @organization_team_required_by_args
    def get(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')
        path = request.args.get('path', None)
        if not path:
            return response_message(EINVAL, 'field path can not be empty'), 401
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)
        pic_root_root = Path(os.path.dirname(pic_root))

        for f in os.listdir(pic_root_root / path):
            if os.path.isdir(pic_root_root / path / f):
                paths.append({'value': f, 'label': f})
        return paths

    @api.doc('create a directory under the specified path')
    @token_required
    @organization_team_required_by_json
    def post(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return response_message(EINVAL, 'field path can not be empty'), 401
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)

        pic_root_root = Path(os.path.dirname(pic_root))
        if (pic_root_root / path).exists():
            return response_message(EEXIST)
        os.mkdir(pic_root_root / path)

        return response_message(SUCCESS)

    @api.doc('delete a directory under the specified path')
    @token_required
    @organization_team_required_by_json
    def delete(self, **kwargs):
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return response_message(EINVAL, 'field path can not be empty'), 401
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')
        if path == '.' or path == './':
            return response_message(EPERM, 'root directory can not be deleted')
        if path == language or path == '.' + os.path.sep + language:
            return response_message(EPERM, 'language directory can not be deleted')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        paths = []
        if proprietary:
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)

        pic_root_root = Path(os.path.dirname(pic_root))
        if not (pic_root_root / path).exists():
            return response_message(ENOENT)
        shutil.rmtree(pic_root_root / path)

        return response_message(SUCCESS)

@api.route('/pictures')
class DocumentRoots(Resource):
    @api.doc('return pictures under a path')
    @token_required
    @organization_team_required_by_args
    def get(self, **kwargs):
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')
        path = request.args.get('path', None)
        if not path:
            return response_message(EINVAL)
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        if proprietary:
            organization = request.args.get('organization', None)
            team = request.args.get('team', None)
            if not organization and not team:
                return response_message(EINVAL)
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)
        pic_root_root = Path(os.path.dirname(pic_root))

        fileList = []
        for f in os.listdir(pic_root_root / path):
            fileName = pic_root_root / path / f
            if os.path.isdir(fileName):
                continue
            _, ext = os.path.splitext(f)
            with open(fileName, 'rb') as pic:
                data = pic.read()
                fileList.append({
                    'name': f,
                    'data': base64.b64encode(data).decode('ascii'),
                    'type': f'image/{ext[1:]}',
                    'size': os.path.getsize(fileName)
                })
        return response_message(SUCCESS, fileList=fileList)

    @api.doc('upload pictures to a path')
    @token_required
    @organization_team_required_by_form
    def post(self, **kwargs):
        proprietary = js2python_bool(request.form.get('proprietary', False))
        language = request.form.get('language', 'en')
        path = request.form.get('path', None)
        if not path:
            return response_message(EINVAL)
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        if proprietary:
            organization = request.form.get('organization', None)
            team = request.form.get('team', None)
            if not organization and not team:
                return response_message(EINVAL)
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)
        pic_root_root = Path(os.path.dirname(pic_root))

        for k in request.files:
            request.files[k].save(pic_root_root / path / k)

        return response_message(SUCCESS)

    @api.doc('remove a picture under a path')
    @token_required
    @organization_team_required_by_json
    def delete(self, **kwargs):
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        path = request.json.get('path', None)
        if not path:
            return response_message(EINVAL)
        path.lstrip('/').lstrip('\\')
        if not is_path_secure(path):
            return response_message(EINVAL, 'Illegal path')

        _, ext = os.path.splitext(path)
        if ext:
            path = os.path.dirname(path)

        if proprietary:
            organization = request.json.get('organization', None)
            team = request.json.get('team', None)
            if not organization and not team:
                return response_message(EINVAL)
            pic_root = get_pictures_root(language, organization, team)
        else:
            pic_root = get_pictures_root(language, None, None)
        if not pic_root.exists():
            os.mkdir(pic_root)
        pic_root_root = Path(os.path.dirname(pic_root))

        filename = request.json.get('filename')
        os.remove(pic_root_root / path / filename)

        return response_message(SUCCESS)

@api.route('/<path:file_path>')
class DocumentCRUD(Resource):
    @api.doc('return markdown file content')
    @token_required
    @organization_team_required_by_args
    def get(self, file_path, **kwargs):
        if not file_path:
            file_path = 'home.md'
        if file_path.endswith('/'):
            file_path = file_path[:-1]
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.args.get('proprietary', False))
        language = request.args.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            return response_message(ENOENT)
        doc.view_times += 1
        doc.save()
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        doc_root_root = Path(os.path.dirname(doc_root))

        try:
            subprocess.run(['git', 'checkout', language], cwd=doc_root_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return response_message(ENOENT, 'file not found')

        with open(os.path.abspath(doc_root / doc.path)) as f:
            return response_message(SUCCESS, content=f.read(), locked=doc.locked)

    @api.doc('update a markdown file')
    @token_required
    @organization_team_required_by_json
    def post(self, file_path, **kwargs):
        if not file_path:
            return response_message(EINVAL, 'file\'s path is required'), 401
        if not is_path_secure(file_path):
            return response_message(EINVAL, 'Illegal path')

        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.json.get('proprietary', False))
        user = kwargs.get('user', None)
        assert user != None
        doc_content = request.json.get('doc_content', '')
        language = request.json.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'filename': os.path.basename(file_path), 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            if not check_editable(None, user, organization, team, proprietary):
                return response_message(EACCES), 401
            doc = Documentation(**query)
            doc.uploader = user
        else:
            if not check_editable(doc, user, organization, team):
                return response_message(EACCES), 401
            doc.last_modified = datetime.datetime.utcnow()
            doc.last_modifier = user
        if file_path == 'home.md':
            doc.locked = True
        doc.save()

        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        if not doc_root.exists():
            os.makedirs(doc_root)

        doc_root_root = Path(os.path.dirname(doc_root))
        git_root = doc_root_root / 'doc.git'
        if not git_root.exists():
            os.makedirs(git_root)
            try:
                subprocess.run(['git', '--bare', 'init'], cwd=git_root, check=True)
            except subprocess.CalledProcessError:
                return response_message(UNKNOWN_ERROR, "git init error"), 500

        if not (doc_root_root / '.git').exists():
            with open(doc_root_root / '.gitignore', 'w') as f:
                f.write('doc.git\n')
            with open(doc_root_root / '.revision', 'w') as f:
                f.write('0')
            try:
                subprocess.run(['git', 'init'], cwd=doc_root_root, check=True)
            except subprocess.CalledProcessError:
                return response_message(UNKNOWN_ERROR, "git local init error"), 500
            try:
                subprocess.run(['git', 'remote', 'add', 'origin', os.path.abspath(git_root)], cwd=doc_root_root, check=True)
            except subprocess.CalledProcessError as e:
                return response_message(UNKNOWN_ERROR, "git remote add error"), 500

            git_checkout_add_push(doc_root_root, 'master', new_branch=True)

        try:
            subprocess.run(['git', 'checkout', language], cwd=doc_root_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            try:
                subprocess.run(['git', 'checkout', '--orphan', language], cwd=doc_root_root, check=True)
            except subprocess.CalledProcessError:
                return response_message(UNKNOWN_ERROR, "git checkout branch error"), 500
            else:
                for f in os.listdir(doc_root_root):
                    if f != 'doc.git' and f != '.git' and f != '.gitignore' and f != language:
                        try:
                            os.unlink(doc_root_root / f)
                        except OSError:
                            shutil.rmtree(doc_root_root / f)
                with open(doc_root_root / '.revision', 'w') as f:
                    f.write('0')

        dirname = os.path.dirname(doc.path)
        if dirname and not (doc_root / dirname).exists():
            os.makedirs(doc_root / dirname)
        with open(doc_root / doc.path, 'w') as f:
            f.write(doc_content)

        git_checkout_add_push(doc_root_root, language)

    @api.doc('delete a markdown file')
    @token_required
    @organization_team_required_by_json
    def delete(self, file_path, **kwargs):
        if not file_path:
            return response_message(EINVAL, 'file\'s path is required'), 401
        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        proprietary = js2python_bool(request.json.get('proprietary', False))
        user = kwargs.get('user', None)
        assert user != None
        language = request.json.get('language', 'en')

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            return response_message(ENOENT, 'document not found'), 404
        if not check_editable(doc, user, organization, team):
            return response_message(EACCES), 401
        if proprietary:
            doc_root = get_document_root(language, organization, team)
        else:
            doc_root = get_document_root(language, None, None)
        doc_root_root = Path(os.path.dirname(doc_root))

        try:
            subprocess.run(['git', 'checkout', language], cwd=doc_root_root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return response_message(ENOENT, 'file not found')

        os.unlink(doc_root / doc.path)
        doc.delete()

        git_checkout_add_push(doc_root_root, language)

        return response_message(SUCCESS)

    @api.doc('lock a document file so that only allowed users can edit it')
    @token_required
    @organization_team_required_by_json
    def patch(self, file_path, **kwargs):
        if not file_path:
            return response_message(EINVAL, 'file\'s path is required'), 401
        if not file_path.endswith('.md'):
            file_path += '.md'
        organization = kwargs.get('organization', None)
        team = kwargs.get('team', None)
        user = kwargs.get('user', None)
        proprietary = js2python_bool(request.json.get('proprietary', False))
        language = request.json.get('language', 'en')
        lock = js2python_bool(request.json.get('lock', None))

        query = {'path': file_path, 'proprietary': proprietary, 'language': language}
        if proprietary:
            query['organization'] = organization
            query['team'] = team
        doc = Documentation.objects(**query).first()
        if not doc:
            return response_message(ENOENT, 'document not found'), 404
        if not check_editable(doc, user, organization, team):
            return response_message(EACCES), 401
        doc.locked = lock
        doc.save()
        return response_message(SUCCESS)
