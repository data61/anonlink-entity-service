import logging
import uuid

import connexion
from flask import g
import structlog

# Define the WSGI application object
# Note we explicitly do this before importing our own code

con_app = connexion.FlaskApp(__name__, specification_dir='api_def', debug=True)
app = con_app.app

try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson


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
# consoleHandler.setFormatter(config.consoleFormat)
structlog.configure(
    processors=[
        # structlog.processors.KeyValueRenderer(
        #     key_order=['event', 'pid', 'rid', 'request'],
        # ),
        structlog.stdlib.add_logger_name,
        #structlog.stdlib.add_log_level,    # Added by unicorn
        structlog.stdlib.PositionalArgumentsFormatter(),
        #structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()  # <=== TODO dev/debug only?
    ],
    context_class=structlog.threadlocal.wrap_dict(dict),
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object(config)

gunicorn_logger = logging.getLogger('gunicorn.error')
# Use the gunicorn logger handler (it owns stdout)
app.logger.handlers = gunicorn_logger.handlers
# Use the logging level passed to gunicorn on the cmd line
app.logger.setLevel(gunicorn_logger.level)

if config.LOGFILE is not None:
   app.logger.addHandler(fileHandler)



@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialized the database.')


@app.before_request
def before_request():
    log = logger.new(request=str(uuid.uuid4())[:8])
    g.db = db.connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()



if __name__ == '__main__':
    con_app.run(debug=True, port=8851)
