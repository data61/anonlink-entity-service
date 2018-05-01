import logging
from flask import Flask, g
from flask_restful import Api

# Define the WSGI application object
# Note we explicitly do this before importing our own code
app = Flask(__name__)

try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson

from entityservice import database as db
from entityservice.serialization import load_public_key, generate_scores
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.utils import fmt_bytes, iterable_to_stream


from entityservice.views import Status, Version, ProjectList, Project, ProjectClks
from entityservice.views.run import RunList, Run, RunStatus, RunResult

# Logging setup
if config.LOGFILE is not None:
    fileHandler = logging.FileHandler(config.LOGFILE)
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(config.fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.DEBUG)
consoleHandler.setFormatter(config.consoleFormat)


# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object(config)
# Add loggers to app
del app.logger.handlers[:]
app.logger.propagate = False
if config.LOGFILE is not None:
    app.logger.addHandler(fileHandler)
app.logger.addHandler(consoleHandler)

# Create our flask_restful api
api = Api(app)


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialized the database.')


api.add_resource(ProjectList, '/projects', endpoint='project-list')
api.add_resource(Project, '/projects/<project_id>', endpoint='project-description')
api.add_resource(ProjectClks, '/projects/<project_id>/clks', endpoint='project-clk-upload')

api.add_resource(RunList, '/projects/<project_id>/runs', endpoint='run-list')
api.add_resource(Run, '/projects/<project_id>/runs/<run_id>', endpoint='run-description')
api.add_resource(RunStatus, '/projects/<project_id>/runs/<run_id>/status', endpoint='run-status')
api.add_resource(RunResult, '/projects/<project_id>/runs/<run_id>/result', endpoint='run-result')

api.add_resource(Status, '/status', endpoint='status')
api.add_resource(Version, '/version', endpoint='version')


@app.before_request
def before_request():
    g.db = db.connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


@app.errorhandler(404)
def not_found(error):
    return "TODO - 404 as PROBLEM"


if __name__ == '__main__':
    app.run(debug=True, port=8851)
