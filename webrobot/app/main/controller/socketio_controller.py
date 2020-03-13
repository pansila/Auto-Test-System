from flask_socketio import send, emit, join_room, leave_room, rooms
from flask import request
from ..service.auth_helper import Auth
from ..util import get_room_id
from task_runner.runner import ROOM_MESSAGES

ROOMS = {}

def handle_message(message):
    print(message, request.sid)

def handle_join_room(json):
    if Auth.is_user_authenticated(json['X-Token']):
        org_team = get_room_id(json)
        join_room(org_team)

        if org_team not in ROOMS:
            ROOMS[org_team] = [request.sid]
        else:
            ROOMS[org_team].append(request.sid)
    if 'task_id' not in json:
        return
    task_id = json['task_id']
    if org_team in ROOM_MESSAGES and task_id in ROOM_MESSAGES[org_team]:
        emit('console log', {'task_id': task_id, 'message': ROOM_MESSAGES[org_team][task_id].decode()})

def handle_leave_room(json):
    if Auth.is_user_authenticated(json['X-Token']):
        org_team = get_room_id(json)
        leave_room(org_team)

        if org_team not in ROOMS:
            return
        elif request.sid in ROOMS[org_team]:
            ROOMS[org_team].remove(request.sid)
