import os
import unittest
if os.name != 'nt':
    from eventlet import monkey_patch
    monkey_patch(os=False)

from flask_script import Manager
from flask_cors import CORS

from app import blueprint
from app.main import create_app
from mongoengine import connect
from app.main.config import get_config
from task_runner.runner import start_event_thread, start_heartbeat_thread, start_rpc_proxy
from flask_socketio import SocketIO, send, emit
from app.main.controller.socketio_controller import handle_message, \
            handle_join_room, handle_enter_room, handle_leave_room

app = create_app(os.getenv('BOILERPLATE_ENV') or 'dev')
get_config().init_app(app)
app.register_blueprint(blueprint)

async_mode = 'threading' if os.name == 'nt' else 'eventlet'
cors_allowed_origins = '*' if os.getenv('BOILERPLATE_ENV') != 'prod' else None
socketio = SocketIO(app, async_mode=async_mode, cors_allowed_origins=cors_allowed_origins)

app.config['socketio'] = socketio

app.app_context().push()
if os.getenv('BOILERPLATE_ENV') != 'prod':
    CORS(app)

manager = Manager(app)


@manager.command
def run():
    connect(get_config().MONGODB_DATABASE, host=get_config().MONGODB_URL, port=get_config().MONGODB_PORT)
    # workaround for dual runnings of the server
    if 'WERKZEUG_RUN_MAIN' in os.environ and os.environ['WERKZEUG_RUN_MAIN'] == 'true':
        start_event_thread(app)
        start_heartbeat_thread(app)
        start_rpc_proxy(app)
    #app.run(host='0.0.0.0')
    socketio.run(app, host='0.0.0.0')

@manager.command
def test():
    """Runs the unit tests."""
    tests = unittest.TestLoader().discover('app/test', pattern='test*.py')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if result.wasSuccessful():
        return 0
    return 1

socketio.on_event('message', handle_message)
socketio.on_event('join', handle_join_room)
socketio.on_event('enter', handle_enter_room)
socketio.on_event('leave', handle_leave_room)

@socketio.on('connect')
def test_connect():
    print('Client connected')

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    manager.run()
