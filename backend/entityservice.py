import json
import os
import logging
import binascii

import psycopg2
from psycopg2.extras import Json

from flask import Flask, g, request
from flask_restful import Resource, Api, abort, fields, marshal_with, marshal
from phe import paillier
import anonlink
from database import connect_db, query_db
from serialization import deserialize_filters
from async_worker import calculate_mapping

# Logging config
LOGFILE = os.environ.get("LOGFILE", 'entity-service-application.log')
fileFormat = logging.Formatter('%(asctime)-15s %(name)-12s %(levelname)-8s: %(message)s')
consoleFormat = logging.Formatter('%(asctime) %(name)-12s: %(levelname)-8s %(message)s', datefmt="%m-%d %H:%M")

# Logging setup
fileHandler = logging.FileHandler(LOGFILE)
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(consoleFormat)
app = Flask(__name__)

# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object('settings.Config')

# Add loggers to app
app.logger.addHandler(fileHandler)
app.logger.addHandler(consoleHandler)
app.logger.setLevel(logging.DEBUG)

# Create our flask_restful api
api = Api(app)


class MappingDao(object):
    """
    A python object for a newly created mapping.

    Exists before insertion into the database.
    """
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
    resource_exists = query_db(get_db(), 'select count(*) from mappings WHERE resource_id = %s', [resource_id], one=True)['count'] == 1
    if not resource_exists:
        app.logger.warning("Request to PUT data with invalid auth token")
        abort(404, message="Mapping {} doesn't exist".format(resource_id))


def abort_if_invalid_dataprovider_token(update_token):
    app.logger.debug("checking authorization token to update data")
    resource_exists = query_db(get_db(), 'select count(*) from dataproviders WHERE token = %s', [update_token], one=True)['count'] == 1
    if not resource_exists:
        abort(403, message="Invalid update token")


def abort_if_invalid_results_token(resource_id, results_token):
    app.logger.debug("checking authorization token to fetch results data")
    resource_exists = query_db(get_db(), """
        select count(*) from mappings
        WHERE
          resource_id = %s AND
          access_token = %s
        """, [resource_id, results_token], one=True)['count'] == 1
    if not resource_exists:
        abort(403, message="Invalid access token")


def abort_if_invalid_receipt_token(resource_id, receipt_token):
    app.logger.debug("checking authorization token to fetch mask data")
    query_result = query_db(get_db(), """
        select dp from dataproviders, bloomingdata, mappings
        WHERE
          bloomingdata.dp = dataproviders.id AND
          dataproviders.mapping = mappings.id AND
          mappings.resource_id = %s AND
          bloomingdata.token = %s
        """, [resource_id, receipt_token], one=True)

    if query_result is None:
        abort(403, message="Invalid access token")

    return query_result['dp']


def generate_code(length=24):
    return binascii.hexlify(os.urandom(length)).decode('utf8')



new_mapping_fields = {
    'resource_id': fields.String,
    'result_token': fields.String,
    'update_tokens': fields.List(fields.String)
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
        for mapping in query_db(get_db(), 'select resource_id, ready from mappings'):
            marshaled_mappings.append(marshal(mapping, mapping_resource_fields))

        return {"mappings": marshaled_mappings}

    @marshal_with(new_mapping_fields)
    def post(self):
        """Create a new mapping

        By default the mapping will be between two organisations.

        There are two types, a "mapping" and a "permutation". The second
        requires a paillier public key to be passed in.
        """
        data = request.get_json()

        if data is None or 'schema' not in data:
            abort(400, message="Schema information required")

        if 'result_type' not in data or data['result_type'] not in {'permutation', 'mapping'}:
            abort(400, message='result-type must be either "permutation" or "mapping"')

        if data['result_type'] == 'permutation' and 'public_key' not in data:
            abort(400, message='Paillier public key required when result_type="permutation"')

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
                (resource_id, access_token, ready, schema, notes, parties, result_type)
                VALUES
                (%s, %s, false, %s, null, %s, %s)
                RETURNING id;
                """,
                [resource_id, mapping.result_token, Json(data['schema']), 2, data['result_type']]
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
                    RETURNING id
                    """,
                    [resource_id, auth_token]
                )
                dp_id = cur.fetchone()[0]
                app.logger.info("Added dataprovider with id = {}".format(dp_id))

                # if data['result_type'] == 'permutation':
                #     app.logger.debug("Creating placeholder masks for permutation")
                #     cur.execute("""
                #         INSERT INTO maskdata
                #         (dp, raw)
                #         VALUES
                #         (%s, %s)
                #         """,
                #         [dp_id, Json("")]

            app.logger.debug("Added data providers")

            app.logger.debug("Committing transaction")
            conn.commit()

        return mapping


class Mapping(Resource):

    def get(self, resource_id):
        """
        This endpoint reveals the results of the calculation.
        What you're allowed to know depends on who you are.
        """
        data = request.get_json()

        if data is None or 'token' not in data:
            abort(401, message="Authentication token required")

        # Check the resource exists
        abort_if_mapping_doesnt_exist(resource_id)

        mapping = query_db(get_db(), "SELECT * from mappings WHERE resource_id = %s",
            [resource_id], one=True)

        app.logger.info("Checking credentials")

        if mapping['result_type'] == 'mapping':
            # Check the caller has a valid results token if we are including results
            abort_if_invalid_results_token(resource_id, data['token'])
        elif mapping['result_type'] == 'permutation':
            dp_id = abort_if_invalid_receipt_token(resource_id, data['token'])

        app.logger.info("Checking for results")
        # Check that the mapping is ready
        if not mapping['ready']:
            # return compute time elapsed here
            time_elapsed = query_db(get_db(),
                                    "SELECT (now() - time_added) as elapsed from mappings WHERE resource_id = %s",
                                    [resource_id], one=True)['elapsed']
            app.logger.debug("Time elapsed so far: {}".format(time_elapsed))
            return {'message': "Mapping isn't ready.", "elapsed": time_elapsed.total_seconds()}, 503

        if mapping['result_type'] == 'mapping':
            app.logger.info("Mapping result being returned")
            return mapping['result']
        elif mapping['result_type'] == 'permutation':
            app.logger.info("Permutation result being returned")
            raise NotImplementedError()
        else:
            app.logger.warning("Unimplemented result type")

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

        mapping = query_db(get_db(), """
            SELECT * from mappings
            WHERE resource_id = %s
        """,
           [resource_id], one=True)
        app.logger.info("Request to add data to mapping")

        # Check the caller has valid token
        abort_if_invalid_dataprovider_token(data['token'])

        dp_id = query_db(get_db(), 'select id from dataproviders WHERE token = %s', [data['token']], one=True)['id']

        app.logger.info("Adding data to: {}".format(dp_id))
        receipt_token = add_mapping_data(dp_id, data['clks'])

        # Now work out if all parties have added their data
        if check_mapping(mapping):
            app.logger.info("Ready to match some entities")
            calculate_mapping.delay(resource_id)
            app.logger.info("Matching job scheduled with celery worker")

        return {'message': 'Updated', 'receipt-token': receipt_token}, 201


class Status(Resource):

    def get(self):
        """Displays the latest mapping statistics"""

        # We ensure we can connect to the database during the status check
        number_of_mappings = query_db(get_db(), '''
            select COUNT(*) from mappings
            ''', one=True)['count']

        return {'status': 'ok', 'number_mappings': number_of_mappings}


def check_mapping(mapping):
    """ See if the given mapping has had all parties contribute data.
    """
    app.logger.info("Counting contributing parties")
    parties_contributed = query_db(get_db(), """
        SELECT COUNT(*)
        FROM dataproviders
        WHERE
          mapping = %s AND uploaded = TRUE
        """, [mapping['id']], one=True)['count']

    app.logger.info("{} parties have contributed blooming data so far".format(parties_contributed))

    return parties_contributed == mapping['parties']


def add_mapping_data(dp_id, clks):
    # TODO add some checks for the clks data

    receipt_token = generate_code()

    conn = get_db()
    with conn.cursor() as cur:
        app.logger.debug("Adding blooming data")
        cur.execute("""
            INSERT INTO bloomingdata
            (dp, token, raw)
            VALUES
            (%s, %s, %s)
            """,
            [dp_id, receipt_token, Json(clks)])

        cur.execute("""
            UPDATE dataproviders
            SET uploaded = TRUE
            WHERE id = %s
            """, [dp_id])

    conn.commit()
    return receipt_token


api.add_resource(MappingList, '/mappings', endpoint='mapping-list')
api.add_resource(Mapping, '/mappings/<resource_id>', endpoint='mapping')
api.add_resource(Status, '/status', endpoint='status')




def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = connect_db()
    return db


@app.before_request
def before_request():
    g.db = connect_db()


@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db'):
        g.db.close()


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
