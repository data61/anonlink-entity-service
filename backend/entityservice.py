import json
import os
import logging
import binascii
from flask import Flask, g, request
from flask_restful import Resource, Api, abort, fields, marshal_with, marshal
from pympler import muppy, summary, tracker

import anonlink
import cache
import database as db
from serialization import load_public_key, deserialize_filters
from async_worker import calculate_mapping
from settings import Config as config

app = Flask(__name__)

# Logging setup
if config.LOGFILE is not None:
    fileHandler = logging.FileHandler(config.LOGFILE)
    fileHandler.setLevel(logging.INFO)
    fileHandler.setFormatter(config.fileFormat)
consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.DEBUG)
consoleHandler.setFormatter(config.consoleFormat)


# Config could be Config, DevelopmentConfig or ProductionConfig
app.config.from_object('settings.Config')

# Add loggers to app
del app.logger.handlers[:]
app.logger.propagate = False
if config.LOGFILE is not None:
    app.logger.addHandler(fileHandler)
app.logger.addHandler(consoleHandler)

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
    resource_exists = db.check_mapping_exists(get_db(), resource_id)
    if not resource_exists:
        app.logger.warning("Requested resource with invalid identifier token")
        abort(404, message="Mapping {} doesn't exist".format(resource_id))


def abort_if_invalid_dataprovider_token(update_token):
    app.logger.debug("checking authorization token to update data")
    resource_exists = db.check_update_auth(get_db(), update_token)
    if not resource_exists:
        abort(403, message="Invalid update token")


def abort_if_invalid_results_token(resource_id, results_token):
    app.logger.debug("checking authorization token to fetch results data")
    valid_access = db.check_mapping_auth(get_db(), resource_id, results_token)
    if not valid_access:
        abort(403, message="Invalid access token")


def abort_if_invalid_receipt_token(resource_id, receipt_token):
    app.logger.debug("checking authorization token to fetch mask data")
    dp_id = db.select_dataprovider_id(get_db(), resource_id, receipt_token)
    if dp_id is None:
        abort(403, message="Invalid access token")
    return dp_id


def abort_if_invalid_token(resource_id, token):
    app.logger.debug("checking authorization token to fetch results data")
    valid_access = db.check_mapping_auth(get_db(), resource_id, token)
    if not valid_access:
        app.logger.debug("checking authorization token to fetch permutation data")
        dp_id = db.select_dataprovider_id(get_db(), resource_id, token)
        if dp_id is None:
            abort(403, message="Invalid access token")
    else:
        dp_id = "Coordinator"
    return dp_id


def check_public_key(pk):
    """
    Check we can unmarshal the public key, and that it has sufficient length.
    """
    publickey = load_public_key(pk)
    return publickey.max_int > 2**1024


def generate_code(length=24):
    return binascii.hexlify(os.urandom(length)).decode('utf8')

new_mapping_fields = {
    'resource_id': fields.String,
    'result_token': fields.String,
    'update_tokens': fields.List(fields.String)
}


class MappingList(Resource):

    """
    A list of all mappings along with their status.
    """

    def get(self):
        mapping_resource_fields = {
            'resource_id': fields.String,
            'ready': fields.Boolean,
            'time_added': fields.DateTime(dt_format='iso8601'),
            'time_completed': fields.DateTime(dt_format='iso8601')
        }

        marshaled_mappings = []

        app.logger.debug("Getting list of all mappings")
        for mapping in db.query_db(get_db(),
                                   'select resource_id, ready, time_added, time_completed from mappings'):
            marshaled_mappings.append(marshal(mapping, mapping_resource_fields))

        return {"mappings": marshaled_mappings}

    @marshal_with(new_mapping_fields)
    def post(self):
        """Create a new mapping

        By default the mapping will be between two organisations.

        There are two types, a "mapping" and a "permutation".

        The permutation type requires a paillier public key to be
        passed in. It takes significantly longer as it has to encrypt
        a mask vector.

        The "permutation_unencrypted_mask" does a permutation but do not encrypt the mask which is
        only sends to the coordinator.
        """
        data = request.get_json()

        if data is None or 'schema' not in data:
            abort(400, message="Schema information required")

        if 'result_type' not in data or data['result_type'] not in {'permutation', 'mapping',
                                                                    'permutation_unencrypted_mask'}:
            abort(400, message='result-type must be either "permutation", "mapping" or '
                               '"permutation_unencrypted_mask"')

        if data['result_type'] == 'permutation' and 'public_key' not in data:
            abort(400, message='Paillier public key required when result_type="permutation"')

        if data['result_type'] == 'permutation' and 'paillier_context' not in data:
            abort(400, message='Paillier context required when result_type="permutation"')

        if data['result_type'] == 'permutation' and not check_public_key(data['public_key']):
            abort(400, message='Paillier public key required when result_type="permutation"')

        # TODO Parse input and check for validity
        mapping_resource = generate_code()
        mapping = MappingDao(mapping_resource)

        # Persist the new mapping
        app.logger.info("Adding new mapping to database")

        conn = get_db()
        with conn.cursor() as cur:
            app.logger.debug("Starting database transaction")
            app.logger.debug("Adding mapping")

            # Insert public key
            if data['result_type'] == 'permutation':
                mapping_db_id = db.insert_permutation(cur, data, mapping, mapping_resource)
            elif data['result_type'] == 'mapping':
                mapping_db_id = db.insert_mapping(cur, data, mapping, mapping_resource)
            else:
                mapping_db_id = db.insert_permutation_unencrypted_mask(cur, data, mapping,
                                                                       mapping_resource)

            app.logger.debug("New resource id: {}".format(mapping_db_id))
            app.logger.debug("Creating new data provider entries")

            for auth_token in mapping.update_tokens:
                dp_id = db.insert_dataprovider(cur, auth_token, mapping_db_id)
                app.logger.info("Added dataprovider with id = {}".format(dp_id))

            app.logger.debug("Added data providers")

            app.logger.debug("Committing transaction")
            conn.commit()

        return mapping


class Mapping(Resource):

    def delete(self, resource_id):
        # Check the resource exists
        abort_if_mapping_doesnt_exist(resource_id)
        app.logger.info("Deleting a mapping resource and all data")
        db.delete_mapping(get_db(), resource_id)
        return '', 204

    def get(self, resource_id):
        """
        This endpoint reveals the results of the calculation.
        What you're allowed to know depends on who you are.
        """
        headers = request.headers

        if headers is None or 'Authorization' not in headers:
            abort(401, message="Authentication token required")

        # Check the resource exists
        abort_if_mapping_doesnt_exist(resource_id)

        dbinstance = get_db()
        mapping = db.get_mapping(dbinstance, resource_id)

        app.logger.info("Checking credentials")

        if mapping['result_type'] == 'mapping':
            # Check the caller has a valid results token if we are including results
            abort_if_invalid_results_token(resource_id, headers.get('Authorization'))
        elif mapping['result_type'] == 'permutation':
            dp_id = abort_if_invalid_receipt_token(resource_id, headers.get('Authorization'))
        elif mapping['result_type'] == 'permutation_unencrypted_mask':
            dp_id = abort_if_invalid_token(resource_id, headers.get('Authorization'))

        app.logger.info("Checking for results")
        # Check that the mapping is ready
        if not mapping['ready']:
            # return compute time elapsed and number of comparisons here
            time_elapsed = db.get_mapping_time(dbinstance, resource_id)
            app.logger.debug("Time elapsed so far: {}".format(time_elapsed))

            comparisons = cache.get_progress(resource_id)
            total_comparisons = db.get_total_comparisons_for_mapping(dbinstance, resource_id)

            return {
                       "message": "Mapping isn't ready.",
                       "elapsed": time_elapsed.total_seconds(),
                       "total": str(total_comparisons),
                       "current": str(comparisons),
                       "progress": (comparisons/total_comparisons) if total_comparisons is not 'NA' else 0.0
                   }, 503

        if mapping['result_type'] == 'mapping':
            app.logger.info("Mapping result being returned")
            return {"mapping": mapping['result']}
        elif mapping['result_type'] == 'permutation':
            app.logger.info("Permutation result being returned")
            result = json.loads(mapping['result'])
            perm = db.get_permutation_result(dbinstance, dp_id)
            result['permutation'] = perm
            return {'permutation': result}
        elif mapping['result_type'] == 'permutation_unencrypted_mask':
            app.logger.info("Permutation with unencrypted mask result being returned")
            # result = json.loads(mapping['result'])
            res = db.get_permutation_unencrypted_mask_result(dbinstance, dp_id, mapping)
            #result['permutation_unencrypted_mask'] = res
            return {'permutation_unencrypted_mask': res}
        else:
            app.logger.warning("Unimplemented result type")

    def put(self, resource_id):
        """
        Update a mapping to provide data
        """
        # ensure we read the post data, even though we mightn't need it
        # without this you get occasional nginx errors failed (104:
        # Connection reset by peer) (See issue #195)
        headers = request.headers
        data = request.get_json()
        abort_if_mapping_doesnt_exist(resource_id)
        if headers is None or 'Authorization' not in headers:
            abort(401, message="Authentication token required")

        token = headers['Authorization']

        if data is None or 'clks' not in data:
            abort(400, message="Missing information")

        mapping = db.get_mapping(get_db(), resource_id)
        app.logger.info("Request to add data to mapping")

        # Check the caller has valid token
        abort_if_invalid_dataprovider_token(token)

        dp_id = db.get_dataprovider_id(get_db(), token)

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
        db1 = get_db()
        number_of_mappings = db.query_db(db1, '''
            select COUNT(*) from mappings
            ''', one=True)['count']

        current_rate = db.get_latest_rate(db1)

        return {
            'status': 'ok',
            'number_mappings': number_of_mappings,
            'rate': current_rate
        }


def check_mapping(mapping):
    """ See if the given mapping has had all parties contribute data.
    """
    app.logger.info("Counting contributing parties")
    parties_contributed = db.get_number_parties_uploaded(get_db(), mapping['id'])
    app.logger.info("{} parties have contributed blooming data so far".format(parties_contributed))
    return parties_contributed == mapping['parties']


def add_mapping_data(dp_id, raw_clks):
    # Note we don't do this in the worker, because we don't want
    # to introduce a race condition for uploading & checking clk data.
    receipt_token = generate_code()

    app.logger.info("Deserialisation of filters from json")
    python_filters = deserialize_filters(raw_clks)
    clkcounts = [cnt for _, _, cnt in python_filters]

    db.insert_raw_filter_data(get_db(), raw_clks, dp_id, receipt_token, clkcounts)

    # Preload the redis cache
    cache.set_deserialized_filter(dp_id, python_filters)

    return receipt_token


api.add_resource(MappingList, '/mappings', endpoint='mapping-list')
api.add_resource(Mapping, '/mappings/<resource_id>', endpoint='mapping')
api.add_resource(Status, '/status', endpoint='status')


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    conn = getattr(g, '_db', None)
    if conn is None:
        conn = g._db = db.connect_db()
    return conn


@app.before_request
def before_request():
    g.db = db.connect_db()


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


@app.route('/danger/generate-names')
def generate_name_data():
    data = request.args
    samples = int(data.get("n", "200"))
    proportion = float(data.get("p", "0.75"))
    nl = anonlink.randomnames.NameList(samples * 2)
    s1, s2 = nl.generate_subsets(samples, proportion)
    return json.dumps({"A": s1, "B": s2})


if __name__ == '__main__':
    app.run(debug=True, port=8851)
