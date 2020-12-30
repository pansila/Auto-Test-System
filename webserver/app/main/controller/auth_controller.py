from sanic import Blueprint
from sanic.response import json
from sanic_openapi import doc

from ..model.database import User
from ..service.auth_helper import Auth
from ..util.dto import AuthDto, json_response
from ..util.response import response_message, USER_NOT_EXIST, SUCCESS

user_auth = AuthDto.user_auth

bp = Blueprint('auth', url_prefix='/auth')


@bp.post('/login')
@doc.summary('User login interface')
@doc.consumes(user_auth, location='body')
@doc.produces(json_response)
async def handler(request):
    post_data = request.json
    ret = await Auth.login_user(data=post_data)
    if ret['code'] != SUCCESS[0]:
        return json(ret)

    user = await User.find_one({'email': post_data.get('email')})
    if not user:
        return json(response_message(USER_NOT_EXIST))

    return json(ret)



@bp.post('/logout')
@doc.summary('User logout interface')
@doc.consumes(doc.String(name='X-Token'), location='header')
@doc.produces(json_response)
async def handler(request):
    auth_header = request.headers.get('X-Token')
    return json(await Auth.logout_user(data=auth_header))
