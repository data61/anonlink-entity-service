import logging
from flask import Flask, g
from flask_restful import Api

# Define the WSGI application object
# Note we explicitly do this before importing our own code
app = Flask(__name__)


##
## NB: This Lovecraftian horror circumvents a problem in the way
## Python searches for shared libraries in Alpine Linux. The problem
## is that Alpine's /sbin/ldconfig does not support the '-p' option to
## obtain a list of directories to search for shared libraries, and so
## Python instead relies on GCC to locate shared libraries. However,
## it's obviously overkill to install GCC just to find shared
## libraries, so we instead monkey patch Python's find_library()
## method to do the obvious thing (but only when the built in
## find_library() fails). Note that the associated Alpine issue
## (#4512) is marked as closed, so it's not clear that we can expect
## an upstream fix for this.
##
## The reason why this code is here specifically, is that the only
## time we trigger the problem described above is in the line
##
##   import ijson.backends.yajl2_cffi
##
## below, which in turn calls find_library() and will fail to find the
## libyajl.so library without the monkey patch.
##
## References:
##   Alpine issue:
##     https://bugs.alpinelinux.org/issues/4512
##   Example monkey-patching code:
##     https://stackoverflow.com/a/48241290
##
def fixed_find_library(name):
    from glob import glob
    result = original_find_library(name)
    if result is None:
        for d in ['/usr/local/lib', '/usr/lib', '/lib']:
            prefix = '{0}/lib{1}'.format(d, name)
            for suff in ['so.*', '*.so.*', 'so']:
                f = glob('{0}.{1}'.format(prefix,suff))
                if f:
                    result = f[0]
                    break
    return result

import ctypes.util
original_find_library = ctypes.util.find_library
ctypes.util.find_library = fixed_find_library

##
## End Lovecraftian horror
##

try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson

from entityservice import database as db
from entityservice.serialization import load_public_key, generate_scores
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config
from entityservice.utils import fmt_bytes, iterable_to_stream


from entityservice.views import Status, Version, ProjectList, Project, ProjectClks, Run, RunStatus, RunResult, RunList

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
