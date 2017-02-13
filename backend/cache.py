import redis

import pickle
import tempfile
import logging

import serialization
import database
from object_store import connect_to_object_store
from settings import Config as config

logger = logging.getLogger('cache')
redis_host = config.REDIS_SERVER
redis_pass = config.REDIS_PASSWORD


def connect_to_redis():
    r = redis.StrictRedis(host=redis_host, password=redis_pass, port=6379, db=0)
    return r


def set_deserialized_filter(dp_id, python_filters):
    logger.debug("Pickling filters and storing in redis")
    key = 'clk-pkl-{}'.format(dp_id)
    r = connect_to_redis()
    pickled_filters = pickle.dumps(python_filters)
    r.set(key, pickled_filters)

    return pickled_filters


def get_deserialized_filter(dp_id):
    """Cached, deserialized version.
    """
    logger.debug("Getting filters")
    key = 'clk-pkl-{}'.format(dp_id)
    r = connect_to_redis()

    # Check if this dp_id is already saved in redis?
    if r.exists(key):
        logger.debug("returning filters from cache")
        return pickle.loads(r.get(key))
    else:
        logger.debug("Looking up popcounts and filename from database")
        db = database.connect_db()
        mc = connect_to_object_store()
        serialized_filters_file, popcnts = database.get_filter_metadata(db, dp_id)

        logger.debug("Getting filters from object store")

        # Note this uses already calculated popcounts unlike
        # serialization.deserialize_filters()
        raw_data_response = mc.get_object(config.MINIO_BUCKET, serialized_filters_file)
        python_filters = serialization.binary_unpack_filters(raw_data_response)

        set_deserialized_filter(dp_id, python_filters)
        return python_filters


def remove_from_cache(dp_id):
    logger.debug("Deleting CLKS for DP {} from redis cache".format(dp_id))
    r = connect_to_redis()
    key = 'clk-pkl-{}'.format(dp_id)
    r.delete(key)


def update_progress(comparisons, resource_id):
    r = connect_to_redis()
    key = 'progress-{}'.format(resource_id)
    r.incr(key, comparisons)


def get_progress(resource_id):
    r = connect_to_redis()
    key = 'progress-{}'.format(resource_id)
    res = r.get(key)
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return 0


def get_status():
    r = connect_to_redis()
    key = 'entityservice-status'
    if r.exists(key):
        logger.debug("returning status from cache")
        return pickle.loads(r.get(key))
    else:
        return None


def set_status(status):
    logger.debug("Saving the service status to redis cache")
    r = connect_to_redis()
    r.setex('entityservice-status', 30, pickle.dumps(status))


