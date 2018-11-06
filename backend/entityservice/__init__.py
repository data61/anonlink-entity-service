import logging
import uuid

import connexion
from flask import g
import structlog
try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson

# Define the WSGI application object
# Note we explicitly do this before importing our own code
con_app = connexion.FlaskApp(__name__, specification_dir='api_def', debug=True)
app = con_app.app

import entityservice.views
from entityservice.tracing import initialize_tracer
from flask_opentracing import FlaskTracer
from entityservice import database as db
from entityservice.serialization import generate_scores
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.utils import fmt_bytes, iterable_to_stream

con_app.add_api('swagger.yaml',
                base_path='/',
                strict_validation=config.CONNEXION_STRICT_VALIDATION,
                validate_responses=config.CONNEXION_RESPONSE_VALIDATION)

# Logging setup
logger = structlog.get_logger()
if config.LOGFILE is not None:
    fileHandler = logging.FileHandler(config.LOGFILE)
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(config.fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.DEBUG)
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=structlog.threadlocal.wrap_dict(dict),
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object(config)

gunicorn_logger = logging.getLogger('gunicorn.error')
# Use the gunicorn logger handler (it owns stdout)
app.logger.handlers = gunicorn_logger.handlers
# Use the logging level passed to gunicorn on the cmd line unless DEBUG is set
if config.DEBUG:
    app.logger.setLevel(logging.DEBUG)
else:
    app.logger.setLevel(gunicorn_logger.level)

if config.LOGFILE is not None:
   app.logger.addHandler(fileHandler)

# Tracer setup (currently just trace all requests)
flask_tracer = FlaskTracer(initialize_tracer, True, app)


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialized the database.')


@app.before_request
def before_request():
    log = logger.new(request=str(uuid.uuid4())[:8])
    g.db = db.connect_db()
    g.flask_tracer = flask_tracer


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


if __name__ == '__main__':
    con_app.run(debug=True, port=8851)
