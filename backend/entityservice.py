import json
import os
import logging
import binascii

from contextlib import closing
import psycopg2
from psycopg2.extras import Json

from flask import Flask, g, request
from flask_restful import Resource, Api, reqparse, abort, fields, marshal_with, marshal

import anonlink
from serialization import deserialize_filters

# Logging config
LOGFILE = os.environ.get("LOGFILE", 'entity-service-application.log')
fileFormat = logging.Formatter('%(asctime)-15s %(name)-12s %(levelname)-8s: %(message)s')
consoleFormat = logging.Formatter('%(asctime) %(name)-12s: %(levelname)-8s %(message)s', datefmt="%m-%d %H:%M")

# Logging setup
fileHandler = logging.FileHandler(LOGFILE)
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(fileFormat)


app = Flask(__name__)


# Config
# Hard coded default configuration can be overwritten with environment variables
# Or a configuration file.
# Postgres Database Details
app.config.update(
    DEBUG=os.environ.get("DEBUG", "false") == "true",
    DATABASE_SERVER=os.environ.get('DATABASE_SERVER', 'db'),
    DATABASE_USER=os.environ.get('DATABASE_USER', 'postgres'),
    DATABASE_PASSWORD=os.environ.get('DATABASE_PASSWORD', ''),
    DATABASE='postgres'
)


# Add loggers to app
app.logger.addHandler(fileHandler)
app.logger.setLevel(logging.DEBUG)
api = Api(app)



# TODO remove this object
class MappingDao(object):
    def __init__(self, resource_id, parties=2):
        app.logger.info("Creating mapping")
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


def abort_if_mapping_doesnt_exist(resource_id):
    resource_exists = query_db('select count(*) from mappings WHERE resource_id = %s', [resource_id], one=True)
    if not resource_exists:
        app.logger.warning("Request to PUT data with invalid auth token")
        abort(404, message="Mapping {} doesn't exist".format(resource_id))


def abort_if_invalid_dataprovider_token(update_token):
    app.logger.debug("checking authorization token to update data")
    resource_exists = query_db('select count(*) from dataproviders WHERE token = %s', [update_token], one=True)
    if not resource_exists:
        abort(403, message="Invalid update token")


def generate_code(length=24):
    return binascii.hexlify(os.urandom(length)).decode('utf8')



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
        mapping_resource_fields = {
            'resource_id': fields.String,
            'ready': fields.Boolean,
        }

        marshaled_mappings = []

        app.logger.debug("Getting list of all mappings")
        for mapping in query_db('select (resource_id, ready) from mappings'):
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
        app.logger.info("Adding new mapping to database")

        conn = get_db()
        with conn.cursor() as cur:
            app.logger.debug("Starting database transaction")
            app.logger.debug("Adding mapping")

            cur.execute("""
                INSERT INTO mappings
                (resource_id, access_token, ready, schema, notes, parties)
                VALUES
                (%s, %s, false, '{}', null, %s)
                RETURNING id;
                """,
                [resource_id, mapping.result_token, 2]
            )

            resource_id = cur.fetchone()[0]
            app.logger.debug("New resource id: {}".format(resource_id))
            app.logger.debug("Creating new data provider entries")

            for auth_token in mapping.update_tokens:
                cur.execute("""
                    INSERT INTO dataproviders
                    (mapping, token)
                    VALUES
                    (%s, %s)
                    """,
                    [resource_id, auth_token]
                )
            app.logger.debug("Added dataproviders")

            app.logger.debug("Committing transaction")
            conn.commit()

        return mapping



class Mapping(Resource):


    #@marshal_with(mapping_resource_fields)
    def get(self, resource_id):
        # Check the resource exists
        abort_if_mapping_doesnt_exist(resource_id)

        mapping = query_db("""
            SELECT * from mappings
            WHERE resource_id = %s""",
            [resource_id], one=True)

        app.logger.info("Checking for results")

        # Check the caller has a valid token if we are including results
        #assert args['auth'] == mapping.result_token, 'Invalid results token'

        # Check that the mapping is ready
        if not mapping['ready']:
            return {'message': "Mapping isn't ready. Data added from all parties?"}, 503

        # TODO - Get from cache, or calculate the mapping
        return mapping['mapping']


    def delete(self, resource_id):
        abort_if_mapping_doesnt_exist(resource_id)

        # Check the caller has valid token

        del mappings[resource_id]
        return '', 204


    def put(self, resource_id):
        """
        Update a mapping to provide data
        """
        abort_if_mapping_doesnt_exist(resource_id)
        data = request.get_json()
        if 'token' not in data:
            abort(401, message="Authentication token required")

        if 'clks' not in data:
            abort(400, message="Missing information")

        mapping = query_db("""
            SELECT * from mappings
            WHERE resource_id = %s
        """,
           [resource_id], one=True)
        app.logger.info("Request to add data to mapping")

        # Check the caller has valid token
        abort_if_invalid_dataprovider_token(data['token'])

        dp_id = query_db('select id from dataproviders WHERE token = %s', [data['token']], one=True)['id']

        app.logger.info("Adding data to: {}".format(dp_id))
        add_mapping_data(dp_id, data['clks'])

        # TODO consider queuing work with celery or sqs
        # Now work out if all parties have added their data

        if check_mapping(mapping):
            app.logger.info("Ready to match some entities")
            calculate_mapping(mapping)

        return {'status': 'Updated'}, 201


def get_filter(dp_id):
    raw_json_filter = query_db("""
        SELECT raw
        FROM bloomingdata
        WHERE
          dp = %s
        """, [dp_id], one=True)['raw']

    return deserialize_filters(raw_json_filter)


def calculate_mapping(mapping):
    app.logger.info("Calculating mapping")

    # Get the data provider IDS
    dp_ids = list(map(lambda d: d['id'], query_db("""
        SELECT id
        FROM dataproviders
        WHERE
          mapping = %s AND uploaded = TRUE
        """, [mapping['id']])))

    app.logger.info("Data providers: {}".format(dp_ids))
    assert len(dp_ids) == 2, "Only support two party comparisons at the moment"

    filters1 = get_filter(dp_ids[0])
    filters2 = get_filter(dp_ids[1])

    similarity = anonlink.entitymatch.calculate_filter_similarity(filters1, filters2)
    mapping = anonlink.network_flow.map_entities(similarity, threshold=0.95, method='weighted')

    result = json.dumps(mapping)

    app.logger.info("Mapping calculated!")

    conn = get_db()
    with conn.cursor() as cur:
        app.logger.debug("Adding blooming data")
        cur.execute("""
            UPDATE mappings SET
            mapping = (%s), ready = TRUE

            """,
            [Json(mapping)])

    conn.commit()
    app.logger.info("Mapping saved")


def check_mapping(mapping):
    """ See if the given mapping has had all parties contribute data.
    """
    app.logger.info("Counting contributing parties")
    parties_contributed = query_db("""
        SELECT COUNT(*)
        FROM dataproviders
        WHERE
          mapping = %s AND uploaded = TRUE
        """, [mapping['id']], one=True)['count']

    app.logger.info("{} parties have contributed blooming data so far".format(parties_contributed))

    return parties_contributed == mapping['parties']


def add_mapping_data(dp_id, clks):

    # TODO check data format...

    conn = get_db()
    with conn.cursor() as cur:
        app.logger.debug("Adding blooming data")
        cur.execute("""
            INSERT INTO bloomingdata
            (dp, raw)
            VALUES
            (%s, %s)
            """,
            [dp_id, Json(clks)])

        cur.execute("""
            UPDATE dataproviders
            SET uploaded = TRUE
            WHERE id = %s
            """, [dp_id])

    conn.commit()


api.add_resource(MappingList, '/mappings', endpoint='mapping-list')
api.add_resource(Mapping, '/mappings/<resource_id>', endpoint='mapping')


def connect_db():
    host = app.config['DATABASE_SERVER']
    user = app.config['DATABASE_USER']
    pw = app.config['DATABASE_PASSWORD']
    db = app.config['DATABASE']

    try:
        conn = psycopg2.connect(database=db, user=user, password=pw, host=host)
    except psycopg2.OperationalError:
        app.logger.warning("warning connecting to default postgres db")
        conn = psycopg2.connect(database='postgres', user=user, password=pw, host=host)
    return conn


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = connect_db()
    return db


def query_db(query, args=(), one=False):
    """
    Queries the database and returns a list of dictionaries.

    https://flask-doc.readthedocs.org/en/latest/patterns/sqlite3.html#easy-querying
    """
    with get_db().cursor() as cur:
        cur.execute(query, args)
        rv = [dict((cur.description[idx][0], value)
                   for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv


@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


@app.route('/status')
def status():
    return 'Ok'

@app.route('/stats')
def stats():
    """Displays the latest mapping statistics"""

    number_of_mappings = query_db('''
        select COUNT(*) from mappings
        ''', one=True)['count']

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
    app.run(debug=True, port=8851)
