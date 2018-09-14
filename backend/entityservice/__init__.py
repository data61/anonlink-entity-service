import logging
import connexion
from flask import g

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


con_app.add_api('swagger.yaml', base_path='/', strict_validation=True, validate_responses=True)

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


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialized the database.')


@app.before_request
def before_request():
    g.db = db.connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


if __name__ == '__main__':
    con_app.run(debug=True, port=8851)
