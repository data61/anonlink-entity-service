import json
import os
import logging
import binascii

from contextlib import closing
import psycopg2

from flask import Flask, g, request
from flask_restful import Resource, Api, reqparse, abort, fields, marshal_with, marshal

import anonlink
from serialization import *

# Config

# Hard coded default configuration can be overwritten with environment variables
# Or a configuration file.

# Postgres Database Details
DATABASE_SERVER = os.environ.get('DATABASE_SERVER', 'db')
DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', 'mysecretpassword')
DATABASE = 'postgres'

PER_PAGE = 30
DEBUG = os.environ.get("DEBUG", "false") == "true"
SKIP_AUTH = os.environ.get("SKIP_AUTH", "false") == "true"
SECRET_KEY = 'development key'

# Logging
LOGFILE = os.environ.get("LOGFILE", 'entity-service-application.log')
fileFormat = logging.Formatter('%(asctime)-15s %(name)-12s %(levelname)-8s: %(message)s [in %(pathname)s:%(lineno)d]')
consoleFormat = logging.Formatter('%(asctime) %(name)-12s: %(levelname)-8s %(message)s', datefmt="%m-%d %H:%M")

# Logging setup
fileHandler = logging.FileHandler(LOGFILE)
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.INFO)
consoleHandler.setFormatter(consoleFormat)


app = Flask(__name__)
app.logger.addHandler(fileHandler)
app.logger.addHandler(consoleHandler)
app.logger.setLevel(logging.DEBUG)
api = Api(app)

# For now it is easier not worry about the database
# I'll just use local memory for the mean time.
mappings = {}


class MappingDao(object):
    def __init__(self, resource_id, parties=2):
        self.parties = parties
        self.resource_id = resource_id
        self.result_token = generate_code()

        # Order is important here
        self.update_tokens = [generate_code() for _ in range(parties)]

        self.ready = False

        # These field will not be sent in the response
        self.status = 'not ready'
        self.data = {}

        self.result = {}


    def add_data(self, update_token, clks):
        # TODO check data format...

        self.data[update_token] = deserialize_filters(clks)

        if len(self.data) == self.parties:
            # TODO consider queuing work with celery or sqs
            self.calculate_mapping()

            self.ready = True

    def calculate_mapping(self):
        filters1 = self.data[self.update_tokens[0]]
        filters2 = self.data[self.update_tokens[1]]

        similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
        mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')
        self.result = json.dumps(mapping)


def abort_if_resource_doesnt_exist(resource_id):
    if resource_id not in mappings:
        abort(404, message="Mapping {} doesn't exist".format(resource_id))


def generate_code(length=24):
    return binascii.hexlify(os.urandom(length)).decode('utf8')

mapping_resource_fields = {
    'resource_id': fields.String,
    'ready': fields.Boolean,
}

new_mapping_fields = {
    'resource_id': fields.String,
    'result_token': fields.String,
    'update_tokens': fields.List(fields.String),
    'ready': fields.Boolean,
}


class MappingList(Resource):

    """
    The individual mapping schema in a list
    """

    def get(self):
        marshaled_mappings = []
        for mapping_id in mappings:
            mapping = mappings[mapping_id]
            marshaled_mappings.append(marshal(mapping, mapping_resource_fields))

        return {"mappings": marshaled_mappings}

    @marshal_with(new_mapping_fields)
    def post(self):
        """Create a new mapping

        By default the mapping will be between two entities.
        """
        data = request.json

        # TODO Parse input and check for validity
        resource_id = generate_code()
        mapping = MappingDao(resource_id)

        # Persist the new mapping
        mappings[resource_id] = mapping
        return mapping



class Mapping(Resource):


    #@marshal_with(mapping_resource_fields)
    def get(self, resource_id):
        # Check the resource exists
        abort_if_resource_doesnt_exist(resource_id)


        mapping = mappings[resource_id]

        # Check the caller has a valid token if we are including results
        #assert args['auth'] == mapping.result_token, 'Invalid results token'

        # Check that the mapping is ready
        if not mapping.ready:
            abort(503, message="Mapping isn't ready. Data added from all parties?")

        # TODO - Get from cache, or calculate the mapping
        return mapping.result


    def delete(self, resource_id):
        abort_if_resource_doesnt_exist(resource_id)

        # Check the caller has valid token

        del mappings[resource_id]
        return '', 204


    def put(self, resource_id):
        """
        Update a mapping to provide data
        """
        abort_if_resource_doesnt_exist(resource_id)
        data = request.get_json()

        mapping = mappings[resource_id]
        # Check the caller has valid token
        assert data['token'] in mapping.update_tokens, 'Invalid update token'

        mapping.add_data(data['token'], data['clks'])

        return {'status': 'Updated'}, 201




api.add_resource(MappingList, '/mappings', endpoint='mapping-list')
api.add_resource(Mapping, '/mappings/<resource_id>', endpoint='mapping')

# def connect_db():
#     host = app.config['DATABASE_SERVER']
#     user = app.config['DATABASE_USER']
#     pw = app.config['DATABASE_PASSWORD']
#     db = app.config['DATABASE']
#
#     try:
#         conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
#     except psycopg2.OperationalError:
#         app.logger.warning("warning connecting to default postgres db")
#         conn = psycopg2.connect(database='postgres', user=user, password=pw, host=host)
#     return conn
#
#
# def get_db():
#     """Opens a new database connection if there is none yet for the
#     current application context.
#     """
#     db = getattr(g, '_db', None)
#     if db is None:
#         db = g._db = connect_db()
#     return db
#
#
# def init_db():
#     """Initializes the database (only run if required)."""
#     # The database name
#     db = app.config['DATABASE']
#
#     # Check if the database exists
#     with closing(connect_db()) as conn:
#         cur = conn.cursor()
#         cur.execute("""SELECT count(*) from pg_database WHERE datname = %s""", (db,))
#         if cur.fetchone()[0] == 1:
#             app.logger.info("Database already exists")
#             return
#
#         app.logger.info("Database doesn't exist yet")
#
#         conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
#         conn.cursor().execute("CREATE DATABASE {};".format(db))
#         app.logger.info("DB created")
#
#     app.logger.info("Creating tables")
#     with closing(connect_db()) as conn:
#         with app.open_resource('schema.sql', mode='r') as f:
#             conn.cursor().execute(f.read())
#         conn.commit()
#     app.logger.info("Tables created")
#
#
# def query_db(query, args=(), one=False):
#     """
#     Queries the database and returns a list of dictionaries.
#
#     https://flask-doc.readthedocs.org/en/latest/patterns/sqlite3.html#easy-querying
#     """
#     with get_db().cursor() as cur:
#         cur.execute(query, args)
#         rv = [dict((cur.description[idx][0], value)
#                    for idx, value in enumerate(row)) for row in cur.fetchall()]
#     return (rv[0] if rv else None) if one else rv
#
#
# @app.before_request
# def before_request():
#     g.db = connect_db()
#
#
# @app.teardown_request
# def teardown_request(exception):
#     if hasattr(g, 'db'):
#         g.db.close()

@app.route('/danger/init')
def init():
    init_db()
    return 'Ok'


@app.route('/status')
def status():
    return 'Ok'

@app.route('/stats')
def stats():
    """Displays the latest mapping statistics"""

    number_of_mappings = query_db('''
        select COUNT() from mappings
        where *
        ''', one=True)

    return json.dumps({'number_mappings': number_of_mappings})


@app.route('/version')
def version():
    return 'anonlink: {}'.format(anonlink.__version__)


@app.route('/danger/test')
def test():

    samples = 200
    nl = anonlink.randomnames.NameList(samples * 2)
    s1, s2 = nl.generate_subsets(samples, 0.75)
    keys = ('test1', 'test2')
    filters1 = anonlink.entitymatch.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = anonlink.entitymatch.calculate_bloom_filters(s2, nl.schema, keys)
    similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
    mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')
    return json.dumps(mapping)


if __name__ == '__main__':
    app.run(debug=True, port=8888)
