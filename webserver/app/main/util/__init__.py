from flask import current_app

from ..model.database import *

def push_event(organization, team, code, message=None):
    event = Event(organization=organization, team=team, code=code)
    if message:
        event.message = message
    event.save()

    eventqueue = EventQueue.objects().first()
    if not eventqueue:
        current_app.logger.error('Event queue not found')
        return False

    if not eventqueue.push(event):
        current_app.logger.error('Failed to push the event')
        return False
    return True

def get_room_id(*data):
    if isinstance(data[0], dict):
        organization = ''
        if 'organization' in data[0]:
            organization = data[0]['organization']
        team = ''
        if 'team' in data[0]:
            team = data[0]['team']
    else:
        organization, team = data[0], data[1]
    org_team = organization + ':' + team
    return org_team

def js2python_bool(value):
    if value == 'True' or value == 'true':
        return True
    if bool(value) == value and value:
        return True
    return False
