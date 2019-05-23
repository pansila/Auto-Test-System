import os
from pathlib import Path
from flask import request, send_from_directory
from flask_restplus import Resource
from bson import ObjectId

from app.main.util.decorator import admin_token_required, token_required
from app.main.model.database import User, Organization, Team

from ..service.auth_helper import Auth
from ..util.dto import OrganizationDto
from ..util.errors import *
from ..config import get_config
from ..util.identicon import *

USERS_ROOT = Path(get_config().USERS_ROOT)

api = OrganizationDto.api
_organization = OrganizationDto.organization


@api.route('/')
class OrganizationList(Resource):
    @token_required
    @api.doc('List all organizations associated with the user')
    def get(self, user):
        user_id = user['user_id']
        orgs = Organization.objects(owner=ObjectId(user_id))
        return [{'name': o.name, 'owner': o.owner.username, 'id': str(o.id)} for o in orgs]

    @token_required
    @api.response(201, 'Organization successfully created.')
    @api.doc('create a new organization')
    def post(self, user):
        data = request.json
        name = data.get('name', None)
        if not name:
            return error_message(EINVAL, 'Field name is required'), 400
        
        org = Organization.objects(name=name).first()
        if org:
            return error_message(EEXIST, 'Organization has been registered, please choose another name'), 401

        user = User.objects(pk=user['user_id']).first()
        org = Organization(name=name)
        org.owner = user
        org.save()
        user.organizations.append(org)
        user.save()

        org_root = USERS_ROOT / name
        try:
            os.mkdir(org_root)
        except Exception as e:
            print(e)
            return error_message(EEXIST), 401

        img= render_identicon(hash(name), 27)
        img.save(org_root / ('%s.png' % org.id))
        org.avatar = '%s.png' % org.id
        org.save()

@api.route('/avatar/<org_id>')
class OrganizationAvatar(Resource):
    @api.doc('get the avatar for an organization')
    def get(self, org_id):
        auth_token = request.cookies.get('Admin-Token')
        if auth_token:
            payload = User.decode_auth_token(auth_token)
            if not isinstance(payload, str):
                user = User.objects(pk=payload['sub']).first()
                if user:
                    org = Organization.objects(pk=org_id).first()
                    if org:
                        return send_from_directory(Path(os.getcwd()) / USERS_ROOT / org.name, org.avatar)
                    return error_message(USER_NOT_EXIST, 'Organization not found'), 404
                return error_message(USER_NOT_EXIST), 404
            return error_message(TOKEN_ILLEGAL, payload), 401
        return error_message(TOKEN_REQUIRED), 400
