import asyncio
import os
import unittest

import motor.motor_asyncio
import socketio

from sanic import Blueprint, Sanic
from sanic.log import logger
from sanic_openapi import swagger_blueprint
from sanic_limiter import Limiter, get_remote_address
from sanic_cors import CORS
from simple_bcrypt import Bcrypt

from app.main.config import get_config

development = True if (os.getenv('BOILERPLATE_ENV') or 'dev') == 'dev' else False

app = Sanic('Ember For Test Automation')
app.blueprint(swagger_blueprint)
app.config.from_object(get_config())
bcrypt = Bcrypt(app)

if development:
    # CORS(app)
    # app.config['CORS_SUPPORTS_CREDENTIALS'] = True
    sio = socketio.AsyncServer(async_mode='sanic', cors_allowed_origins='*')
else:
    sio = socketio.AsyncServer(async_mode='sanic')
sio.attach(app)

limits = ['20000 per hour', '200000 per day'] if development else ['200 per hour', '2000 per day']
limiter = Limiter(app, global_limits=limits, key_func=get_remote_address)
event_task = None
heartbeat_task = None
rpc_server = None
db_client = None

@app.listener('before_server_start')
async def setup_connection(app, loop):
    global event_task, heartbeat_task, rpc_server, db_client

    db_client = motor.motor_asyncio.AsyncIOMotorClient(f"{app.config['MONGODB_URL']}:{app.config['MONGODB_PORT']}")
    app.config.db = db_client[app.config['MONGODB_DATABASE']]

    from task_runner.runner import initialize_runner, start_event_thread, start_heartbeat_thread, start_xmlrpc_server
    event_task = asyncio.create_task(start_event_thread(app))
    heartbeat_task = asyncio.create_task(start_heartbeat_thread(app))
    rpc_server = start_xmlrpc_server(app)
    initialize_runner(app)

    from app.main.controller.auth_controller import bp as auth_bp
    from app.main.controller.user_controller import bp as user_bp
    from app.main.controller.organization_controller import bp as organization_bp
    from app.main.controller.team_controller import bp as team_bp
    from app.main.controller.endpoint_controller import bp as endpoint_bp
    from app.main.controller.setting_controller import bp as setting_bp
    from app.main.controller.script_controller import bp as script_bp
    from app.main.controller.teststore_controller import bp as teststore_bp
    from app.main.controller.task_controller import bp as task_bp
    from app.main.controller.taskresource_controller import bp as taskresource_bp
    from app.main.controller.test_controller import bp as test_bp
    from app.main.controller.testresult_controller import bp as testresult_bp
    from app.main.controller.document_controller import bp as document_bp
    from app.main.controller.socketio_controller import handle_message, handle_join_room, handle_enter_room, handle_leave_room
    from task_runner.runner import bp as rpc_bp

    limiter.limit("100 per hour")(user_bp)

    bp_groups = (auth_bp, user_bp, organization_bp, team_bp, endpoint_bp, setting_bp, rpc_bp, script_bp, teststore_bp, task_bp, taskresource_bp, test_bp, testresult_bp, document_bp)
    api_v1 = Blueprint.group(*bp_groups, url_prefix='/api_v1')
    app.blueprint(api_v1)

    sio.on('message', handle_message)
    sio.on('join', handle_join_room)
    sio.on('enter', handle_enter_room)
    sio.on('leave', handle_leave_room)

@app.listener('after_server_start')
async def wait_tasks_ready(app, loop):
    pass

@app.listener('before_server_stop')
async def cleanup(app, loop):
    global event_task, heartbeat_task, rpc_server, db_client
    event_task.cancel()
    heartbeat_task.cancel()
    rpc_server.server.stop()
    db_client.close()


@sio.event
def connect(sid, environ):
    logger.info(f'Client connected, sid: {sid}')

@sio.event
def disconnect(sid):
    logger.info(f'Client disconnected, sid: {sid}')


@app.listener('after_server_stop')
async def close_connection(app, loop):
    pass

def run():
    app.run(host='0.0.0.0', port=5000, debug=True)

def test():
    """Runs the unit tests."""
    tests = unittest.TestLoader().discover('app/test', pattern='test*.py')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if result.wasSuccessful():
        return 0
    return 1

if __name__ == '__main__':
    run()
