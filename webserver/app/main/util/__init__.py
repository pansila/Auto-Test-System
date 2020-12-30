import asyncio
import os
import sys
import shutil
from async_files.utils import async_wraps

from sanic.log import logger

from ..model.database import Event, EventQueue

@asyncio.coroutine
def sleep0():
    """Skip one event loop run cycle.
    This is a private helper for 'asyncio.sleep()', used
    when the 'delay' is set to 0.  It uses a bare 'yield'
    expression (which Task.__step knows how to handle)
    instead of creating a Future object.
    """
    yield

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

def get_room_id(organization, team):
    org_team = organization + ':' + (team if team else '')
    return org_team

def get_room_id_by_json(json):
    assert 'organization' in json
    team = json['team'] if 'team' in json else ''
    return get_room_id(json['organization'], team)

def js2python_bool(value):
    if value == 'True' or value == 'true':
        return True
    if bool(value) == value and value:
        return True
    return False

def js2python_variable(value):
    if not value or value == 'undefined' or value == 'null':
        return None
    return value

class temp_sys_path():
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        sys.path.append(self.path)

    def __exit__(self, exception_type, exception_value, traceback):
        if sys.path.index(self.path) == len(sys.path) - 1:
            sys.path.pop(sys.path.index(self.path))
        else:
            raise Exception('Can\'t find temporary path in the sys.path added before')

async_rmtree = async_wraps(shutil.rmtree)
async_copytree = async_wraps(shutil.copytree)
async_copy = async_wraps(shutil.copy)
async_move = async_wraps(shutil.move)
async_isdir = async_wraps(os.path.isdir)
async_isfile = async_wraps(os.path.isfile)
async_exists = async_wraps(os.path.exists)
async_makedirs = async_wraps(os.makedirs)
async_walk = async_wraps(lambda x: list(os.walk(x)))
async_listdir = async_wraps(os.listdir)
