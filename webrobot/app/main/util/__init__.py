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