import json
import os
import os.path
import io
import platform
import logging
import binascii

from flask import Flask, g, request
from flask_restful import Resource, Api, abort, fields, marshal_with, marshal

try:
    import ijson.backends.yajl2_cffi as ijson
except ImportError:
    import ijson

import anonlink
import cache
import database as db
from serialization import load_public_key, deserialize_filters, binary_pack_filters
from async_worker import calculate_mapping, handle_raw_upload
from object_store import connect_to_object_store
from settings import Config as config
from utils import fmt_bytes


__version__ = open(os.path.join(os.path.dirname(__file__), 'VERSION')).read().strip()

INVALID_ACCESS_MSG = "Invalid access token or mapping doesn't exist"

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


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database after a short delay."""
    db.init_db(5)
    print('Initialized the database.')


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


def safe_fail_request(status_code, message):
    # ensure we read the post data, even though we mightn't need it
    # without this you get occasional nginx errors failed (104:
    # Connection reset by peer) (See issue #195)
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        chunk_size = 4096
        for data in request.input_stream.read(chunk_size):
            pass
    else:
        data = request.get_json()
    abort(http_status_code=status_code, message=message)


def get_stream():
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        stream = request.input_stream
    else:
        stream = request.stream
    return stream


def get_json():
    # Handle chunked Transfer-Encoding...
    if 'Transfer-Encoding' in request.headers and request.headers['Transfer-Encoding'] == 'chunked':
        stream = get_stream()

        def consume_as_string(byte_stream):
            data = []
            while True:
                byte_data = byte_stream.read(4096)
                if byte_data:
                    data.append(byte_data.decode())
                else:
                    break
            return ''.join(data)

        return json.loads(consume_as_string(stream))
    else:
        return request.get_json()


def abort_if_mapping_doesnt_exist(resource_id):
    resource_exists = db.check_mapping_exists(get_db(), resource_id)
    if not resource_exists:
        app.logger.warning("Requested resource with invalid identifier token")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def abort_if_invalid_dataprovider_token(update_token):
    app.logger.debug("checking authorization token to update data")
    resource_exists = db.check_update_auth(get_db(), update_token)
    if not resource_exists:
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def is_results_token_valid(resource_id, results_token):
    if not db.check_mapping_auth(get_db(), resource_id, results_token):
        return False
    else:
        return True


def is_receipt_token_valid(resource_id, receipt_token):
    if db.select_dataprovider_id(get_db(), resource_id, receipt_token) is None:
        return False
    else:
        return True


def abort_if_invalid_results_token(resource_id, results_token):
    app.logger.debug("checking authorization token to fetch results data")
    if not is_results_token_valid(resource_id, results_token):
        app.logger.debug("Auth invalid")
        safe_fail_request(403, message=INVALID_ACCESS_MSG)


def dataprovider_id_if_authorize(resource_id, receipt_token):
    app.logger.debug("checking authorization token to fetch mask data")
    if not is_receipt_token_valid(resource_id, receipt_token):
        safe_fail_request(403, message=INVALID_ACCESS_MSG)

    dp_id = db.select_dataprovider_id(get_db(), resource_id, receipt_token)
    return dp_id


def node_id_if_authorize(resource_id, token):
    """
    In case of a permutation with an unencrypted mask, we are using both the result token and the
    receipt tokens. The result token is used by the coordinator to get the mask. The receipts tokens
    are used by the dataproviders to get their permutations. However, we do not know before checking
    which is the type of the received token.
    """
    app.logger.debug("checking authorization token to fetch results data")
    # If the token is not a valid result token, it should be a receipt token.
    if not is_results_token_valid(resource_id, token):
        app.logger.debug("checking authorization token to fetch permutation data")
        # If the token is not a valid receipt token, we abort.
        if not is_receipt_token_valid(resource_id, token):
            safe_fail_request(403, message=INVALID_ACCESS_MSG)
        dp_id = db.select_dataprovider_id(get_db(), resource_id, token)
    else:
        dp_id = "Coordinator"
    return dp_id


def check_public_key(pk):
    """
    Check we can unmarshal the public key, and that it has sufficient length.
    """
    publickey = load_public_key(pk)
    return publickey.max_int >= 2 ** config.ENCRYPTION_MIN_KEY_LENGTH


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
            'time_started': fields.DateTime(dt_format='iso8601'),
            'time_completed': fields.DateTime(dt_format='iso8601')
        }

        marshaled_mappings = []

        app.logger.debug("Getting list of all mappings")
        for mapping in db.query_db(get_db(),
                                   'select resource_id, ready, time_added, time_started, time_completed from mappings'):
            marshaled_mappings.append(marshal(mapping, mapping_resource_fields))

        return {"mappings": marshaled_mappings}

    @marshal_with(new_mapping_fields)
    def post(self):
        """Create a new mapping

        By default the mapping will be between two organisations.

        There are three types, a "mapping", a "permutation" and a "permutation_unencrypted_mask".

        The permutation type requires a paillier public key to be
        passed in. It takes significantly longer as it has to encrypt
        a mask vector.

        The "permutation_unencrypted_mask" does a permutation but do not encrypt the mask which is
        only sends to the coordinator (owner of the results_token).
        """
        data = get_json()

        if data is None or 'schema' not in data:
            safe_fail_request(400, message="Schema information required")

        if 'result_type' not in data or data['result_type'] not in {'permutation', 'mapping',
                                                                    'permutation_unencrypted_mask'}:
            safe_fail_request(400, message='result_type must be either "permutation", "mapping" or '
                               '"permutation_unencrypted_mask"')

        if data['result_type'] == 'permutation' and 'public_key' not in data:
            safe_fail_request(400, message='Paillier public key required when result_type="permutation"')

        if data['result_type'] == 'permutation' and 'paillier_context' not in data:
            safe_fail_request(400, message='Paillier context required when result_type="permutation"')

        if data['result_type'] == 'permutation' and not check_public_key(data['public_key']):
            safe_fail_request(400, message='Paillier public key required when result_type="permutation"')

        mapping_resource = generate_code()
        mapping = MappingDao(mapping_resource)

        threshold = data.get('threshold', config.ENTITY_MATCH_THRESHOLD)
        if threshold <= 0.0 or threshold >= 1.0:
            safe_fail_request(400, message="Threshold parameter out of range")

        app.logger.debug("Threshold for mapping is {}".format(threshold))

        # Persist the new mapping
        app.logger.info("Adding new mapping to database")

        conn = get_db()
        with conn.cursor() as cur:
            app.logger.debug("Starting database transaction")
            app.logger.debug("Creating a new mapping")
            mapping_db_id = db.insert_mapping(cur, data['result_type'], data['schema'], threshold, mapping, mapping_resource)

            if data['result_type'] == 'permutation':
                app.logger.debug("Inserting public key and paillier context into db")
                paillier_db_id = db.insert_paillier(cur, data['public_key'], data['paillier_context'])
                db.insert_empty_encrypted_mask(cur, mapping_resource, paillier_db_id)

            app.logger.debug("New mapping created in DB: {}".format(mapping_db_id))
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
        # First get the filenames of everything in the object store

        mc = connect_to_object_store()

        db.delete_mapping(get_db(), resource_id)

        return '', 204

    def get(self, resource_id):
        """
        This endpoint reveals the results of the calculation.
        What you're allowed to know depends on who you are.
        """
        headers = request.headers

        if headers is None or 'Authorization' not in headers:
            safe_fail_request(401, message="Authentication token required")

        # Check the resource exists
        abort_if_mapping_doesnt_exist(resource_id)

        dbinstance = get_db()
        mapping = db.get_mapping(dbinstance, resource_id)

        app.logger.info("Checking credentials")

        if mapping['result_type'] == 'mapping':
            # Check the caller has a valid results token if we are including results
            abort_if_invalid_results_token(resource_id, headers.get('Authorization'))
        elif mapping['result_type'] == 'permutation':
            dp_id = dataprovider_id_if_authorize(resource_id, headers.get('Authorization'))
        elif mapping['result_type'] == 'permutation_unencrypted_mask':
            dp_id = node_id_if_authorize(resource_id, headers.get('Authorization'))
        else:
            safe_fail_request(500, "Unknown error")

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
            result = db.get_mapping_result(dbinstance, resource_id)
            return {
                "mapping": result
            }

        elif mapping['result_type'] == 'permutation':
            app.logger.info("Encrypted permutation result being returned")
            return db.get_permutation_encrypted_result_with_mask(dbinstance, resource_id, dp_id)

        elif mapping['result_type'] == 'permutation_unencrypted_mask':
            app.logger.info("Permutation with unencrypted mask result type")

            if dp_id == "Coordinator":
                app.logger.info("Returning unencrypted mask to coordinator")
                # The mask is a json blob of an
                # array of 0/1 ints
                mask = db.get_permutation_unencrypted_mask(dbinstance, resource_id)
                return {
                    "mask": mask
                }
            else:
                perm = db.get_permutation_result(dbinstance, dp_id)
                rows = db.get_smaller_dataset_size_for_mapping(dbinstance, resource_id)

                return {
                    'permutation': perm,
                    'rows': rows
                }
            # The result in this case is either a permutation, or the encrypted mask.
            # The key 'permutation_unencrypted_mask' is kept for the Java recognition of the algorithm.

        else:
            app.logger.warning("Unimplemented result type")

    def put(self, resource_id):
        """
        Update a mapping to provide data
        """

        # Pass the request.stream to add_mapping_data
        # to avoid parsing the json in one hit, this enables running the
        # web frontend with less memory.
        headers = request.headers

        # Note we don't use request.stream so we handle chunked uploads without
        # the content length set...
        stream = get_stream()

        abort_if_mapping_doesnt_exist(resource_id)
        if headers is None or 'Authorization' not in headers:
            safe_fail_request(401, message="Authentication token required")

        token = headers['Authorization']

        # Check the caller has valid token
        abort_if_invalid_dataprovider_token(token)

        dp_id = db.get_dataprovider_id(get_db(), token)

        app.logger.info("Receiving data for: dpid: {}".format(dp_id))
        receipt_token, raw_file = add_mapping_data(dp_id, stream)

        # Schedule a task to deserialize the hashes, and carry
        # out a pop count.
        handle_raw_upload.delay(resource_id, dp_id, receipt_token)
        app.logger.info("Job scheduled to handle user uploaded hashes")

        return {'message': 'Updated', 'receipt-token': receipt_token}, 201



class MappingStatus(Resource):

    """
    Status of a particular mappings
    """

    def get(self, resource_id):
        mapping_resource_fields = {
            'ready': fields.Boolean,
            'time_added': fields.DateTime(dt_format='iso8601'),
            'time_started': fields.DateTime(dt_format='iso8601'),
            'time_completed': fields.DateTime(dt_format='iso8601'),
            'threshold': fields.Float()
        }

        app.logger.debug("Getting list of all mappings")
        query = '''
        SELECT ready, time_added, time_started, time_completed, threshold
        FROM mappings
        WHERE
        resource_id = %s
        '''

        stats = db.query_db(get_db(), query, (resource_id,), one=True)
        return marshal(stats, mapping_resource_fields)


class Status(Resource):

    def get(self):
        """Displays the latest mapping statistics"""

        status = cache.get_status()

        if status is None:
            # We ensure we can connect to the database during the status check
            db1 = get_db()

            number_of_mappings = db.query_db(db1, '''
                        SELECT COUNT(*) FROM mappings
                        ''', one=True)['count']

            current_rate = db.get_latest_rate(db1)

            status = {
                'status': 'ok',
                'number_mappings': number_of_mappings,
                'rate': current_rate
            }

            cache.set_status(status)
        return status


def add_mapping_data(dp_id, raw_stream):
    """
    Save the untrusted user provided data and start a celery job to
    deserialize, popcount and save the hashes.

    Because this takes place in a worker, we "lock" the upload by
    setting the state to pending in the bloomingdata table.
    """
    receipt_token = generate_code()


    filename = config.RAW_FILENAME_FMT.format(receipt_token)
    app.logger.info("Storing user {} supplied clks from json".format(dp_id))

    # We will increment a counter as we process
    store = {
        'count': 0,
        'totalbytes': 0
    }

    def counting_generator():
        try:
            for clk in ijson.items(raw_stream, 'clks.item'):
                # Often the clients upload base64 strings with newlines
                # We remove those here
                raw = ''.join(clk.split('\n')).encode() + b'\n'
                store['count'] += 1
                store['totalbytes'] += len(raw)
                yield raw
        except ijson.common.IncompleteJSONError as e:
            store['count'] = 0
            app.logger.warning("Stopping as we have received incomplete json")
            return

    # Annoyingly we need the totalbytes to upload to the object store
    # so we consume the input stream here. We could change the public
    # api instead so that we know the expected size ahead of time.
    data = b''.join(counting_generator())
    num_bytes = len(data)
    buffer = io.BytesIO(data)

    if store['count'] == 0:
        abort(400, message="Missing information")


    app.logger.info("Processed {} CLKS".format(store['count']))
    app.logger.info("Uploading {} to object store".format(fmt_bytes(num_bytes)))
    mc = connect_to_object_store()
    mc.put_object(
        config.MINIO_BUCKET,
        filename,
        data=buffer,
        length=len(data)
    )

    db.insert_filter_data(get_db(), filename, dp_id, receipt_token, store['count'])

    return receipt_token, filename


class Version(Resource):

    def get(self):
        return {
            'anonlink': anonlink.__version__,
            'entityservice': __version__,
            'libc': "".join(platform.libc_ver()),
            'python': platform.python_version()
        }


api.add_resource(MappingList, '/mappings', endpoint='mapping-list')
api.add_resource(Mapping, '/mappings/<resource_id>', endpoint='mapping')
api.add_resource(MappingStatus, '/mappings/<resource_id>/status', endpoint='mapping-stats')
api.add_resource(Status, '/status', endpoint='status')
api.add_resource(Version, '/version', endpoint='version')


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


@app.route('/danger/test')
def test():
    samples = 200
    nl = anonlink.randomnames.NameList(samples * 2)
    s1, s2 = nl.generate_subsets(samples, 0.75)
    keys = ('test1', 'test2')
    filters1 = anonlink.bloomfilter.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = anonlink.bloomfilter.calculate_bloom_filters(s2, nl.schema, keys)
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
