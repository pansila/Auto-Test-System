import asyncio
from task_runner.runner import ROOM_MESSAGES
from app import sio
from marshmallow.exceptions import ValidationError

from ..service.auth_helper import Auth
from ..util import get_room_id_by_json
from ..model.database import Organization, Team, Task, Endpoint

def handle_message(sid, message):
    print(message, sid)

async def handle_join_room(sid, json):
    if 'X-Token' not in json:
        return
    if not await Auth.is_user_authenticated(json['X-Token']):
        return

    org_team = get_room_id_by_json(json)
    sio.enter_room(sid, org_team)

    if 'task_id' not in json:
        return
    task_id = json['task_id']

    if org_team in ROOM_MESSAGES and task_id in ROOM_MESSAGES[org_team] and ROOM_MESSAGES[org_team][task_id]:
        await sio.emit('backlog', {'task_id': task_id, 'message': ROOM_MESSAGES[org_team][task_id].getvalue()}, room=org_team)

async def handle_enter_room(sid, json):
    if 'task_id' not in json:
        return
    if 'X-Token' not in json:
        return
    if not await Auth.is_user_authenticated(json['X-Token']):
        return

    org_team = get_room_id_by_json(json)

    task_id = json['task_id']
    if org_team in ROOM_MESSAGES and task_id in ROOM_MESSAGES[org_team] and ROOM_MESSAGES[org_team][task_id]:
        await sio.emit('backlog', {'task_id': task_id, 'message': ROOM_MESSAGES[org_team][task_id].getvalue()}, room=org_team)

async def handle_leave_room(sid, json):
    if 'X-Token' not in json:
        return
    if await Auth.is_user_authenticated(json['X-Token']):
        org_team = get_room_id_by_json(json)
        sio.leave_room(sid, org_team)
