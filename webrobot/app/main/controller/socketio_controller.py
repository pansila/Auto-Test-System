from flask_socketio import send, emit, join_room, leave_room, rooms
from flask import request
from ..service.auth_helper import Auth
from ..util import get_room_id
from task_runner.runner import ROOM_MESSAGES

def handle_message(message):
    print(message, request.sid)

def handle_join_room(json):
    if not Auth.is_user_authenticated(json['X-Token']):
        return

    org_team = get_room_id(json)
    join_room(org_team)

    if 'task_id' not in json:
        return
    task_id = json['task_id']
    if org_team in ROOM_MESSAGES and task_id in ROOM_MESSAGES[org_team] and ROOM_MESSAGES[org_team][task_id]:
        emit('console log', {'task_id': task_id, 'message': ROOM_MESSAGES[org_team][task_id].getvalue()})

def handle_enter_room(json):
    if not Auth.is_user_authenticated(json['X-Token']):
        return

    org_team = get_room_id(json)

    if 'task_id' not in json:
        return
    task_id = json['task_id']
    if org_team in ROOM_MESSAGES and task_id in ROOM_MESSAGES[org_team] and ROOM_MESSAGES[org_team][task_id]:
        emit('console log', {'task_id': task_id, 'message': ROOM_MESSAGES[org_team][task_id].getvalue()})

def handle_leave_room(json):
    if Auth.is_user_authenticated(json['X-Token']):
        org_team = get_room_id(json)
        leave_room(org_team)
