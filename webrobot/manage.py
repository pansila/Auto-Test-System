import os
import unittest

from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager
from flask_cors import CORS

from app import blueprint
from app.main import create_app, db
from app.main.model import user, blacklist
from mongoengine import connect
from app.main.config import get_config

app = create_app(os.getenv('BOILERPLATE_ENV') or 'dev')
app.register_blueprint(blueprint)

app.app_context().push()
if os.getenv('BOILERPLATE_ENV') != 'prod':
    CORS(app)

manager = Manager(app)

migrate = Migrate(app, db)

manager.add_command('db', MigrateCommand)


@manager.command
def run():
    connect(get_config().MONGODB_DATABASE, host=get_config().MONGODB_URL, port=get_config().MONGODB_PORT)
    app.run(host='0.0.0.0')


@manager.command
def test():
    """Runs the unit tests."""
    tests = unittest.TestLoader().discover('app/test', pattern='test*.py')
    result = unittest.TextTestRunner(verbosity=2).run(tests)
    if result.wasSuccessful():
        return 0
    return 1

if __name__ == '__main__':
    manager.run()
