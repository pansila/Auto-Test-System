from flask_restplus import Api
from flask import Blueprint

from .main.controller.user_controller import api as user_ns
from .main.controller.auth_controller import api as auth_ns
from .main.controller.test_controller import api as test_ns
from .main.controller.task_controller import api as task_ns
from .main.controller.testresult_controller import api as testresult_ns
from .main.controller.taskresource_controller import api as taskresource_ns
from .main.controller.endpoint_controller import api as endpoint_ns
from .main.controller.script_controller import api as script_ns
from .main.controller.organization_controller import api as organization_ns
from .main.controller.team_controller import api as team_ns

blueprint = Blueprint('api', __name__)

api = Api(blueprint,
          title='FLASK RESTPLUS API BOILER-PLATE WITH JWT',
          version='1.0',
          description='a boilerplate for flask restplus web service'
          )

api.add_namespace(user_ns, path='/user')
api.add_namespace(auth_ns)
api.add_namespace(test_ns)
api.add_namespace(task_ns)
api.add_namespace(testresult_ns)
api.add_namespace(taskresource_ns)
api.add_namespace(endpoint_ns)
api.add_namespace(script_ns)
api.add_namespace(organization_ns)
api.add_namespace(team_ns)
