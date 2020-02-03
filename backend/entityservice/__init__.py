import pathlib
import uuid
import connexion
from flask import g, request
import structlog
from tenacity import RetryError
try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson

from entityservice.logger_setup import setup_logging

# Logging setup
setup_logging()

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

con_app.add_api(pathlib.Path("swagger.yaml"),
                base_path='/',
                strict_validation=config.CONNEXION_STRICT_VALIDATION,
                validate_responses=config.CONNEXION_RESPONSE_VALIDATION)


# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object(config)

logger = structlog.get_logger()
# Tracer setup (currently just trace all requests)
flask_tracer = FlaskTracer(initialize_tracer, True, app)


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialised the database.')


@app.before_first_request
def before_first_request():
    db_min_connections = config.FLASK_DB_MIN_CONNECTIONS
    db_max_connections = config.FLASK_DB_MAX_CONNECTIONS
    try:
        db.init_db_pool(db_min_connections, db_max_connections)
    except RetryError:
        logger.error("Giving up on connecting to database")
        raise SystemExit("Couldn't establish connection to database pool")


@app.before_request
def before_request():
    g.log = logger.new(request=str(uuid.uuid4())[:8])
    if config.LOG_HTTP_HEADER_FIELDS is not None:
        headers = {}
        for header in config.LOG_HTTP_HEADER_FIELDS.split(','):
            header = header.strip()
            if header in request.headers:
                headers[header] = request.headers[header]
        g.log.bind(**headers)
    g.flask_tracer = flask_tracer


if __name__ == '__main__':
    con_app.run(debug=True, port=8851)
