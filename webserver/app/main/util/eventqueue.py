from sanic.log import logger
from ..model.database import Event, EventQueue

async def push_event(organization, team, code, message=None):
    event = Event(organization=organization, code=code)
    if message:
        event.message = message
    if team:
        event.team = team
    await event.commit()

    eventqueue = await EventQueue.find_one({})
    if not eventqueue:
        logger.error('Event queue not found')
        return False

    try:
        await eventqueue.push(event)
    except RuntimeError:
        logger.error('Failed to push the event')
        return False
    return True
