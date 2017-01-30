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


def set_deserialized_filter(dp_id, python_filters):
    logger.debug("Pickling filters and storing in redis")
    key = 'clk-pkl-{}'.format(dp_id)
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    pickled_filters = pickle.dumps(python_filters)
    r.set(key, pickled_filters)

    return pickled_filters


def get_deserialized_filter(dp_id):
    """Cached, deserialized version.
    """
    logger.debug("Getting filters")
    key = 'clk-pkl-{}'.format(dp_id)
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)

    # Check if this dp_id is already saved in redis?
    if r.exists(key):
        logger.debug("returning filters from cache")
        return pickle.loads(r.get(key))
    else:
        logger.debug("Looking up popcounts and filename from database")
        db = database.connect_db()
        mc = connect_to_object_store()
        serialized_filters_file, popcnts = database.get_filter(db, dp_id)

        logger.debug("Getting filters from object store")

        python_filters = []
        with tempfile.NamedTemporaryFile('w') as f:
            mc.fget_object(config.MINIO_BUCKET, serialized_filters_file, f.name)

            # Note this uses already calculated popcounts unlike
            # serialization.deserialize_filters()
            for i, (f, cnt) in enumerate(zip(json_serialized_filters, popcnts)):
                ba = serialization.deserialize_bitarray(f)
                python_filters.append((ba, i, cnt))

        set_deserialized_filter(dp_id, python_filters)
        return python_filters


def remove_from_cache(dp_id):
    logger.debug("Deleting CLKS for DP {} from redis cache".format(dp_id))
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    key = 'clk-pkl-{}'.format(dp_id)
    r.delete(key)


def update_progress(comparisons, resource_id):
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    key = 'progress-{}'.format(resource_id)
    r.incr(key, comparisons)


def get_progress(resource_id):
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    key = 'progress-{}'.format(resource_id)
    res = r.get(key)
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return 0


def get_status():
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    key = 'entityservice-status'
    if r.exists(key):
        logger.debug("returning status from cache")
        return pickle.loads(r.get(key))
    else:
        return None


def set_status(status):
    logger.debug("Saving the service status to redis cache")
    r = redis.StrictRedis(host=redis_host, port=6379, db=0)
    r.setex('entityservice-status', 30, pickle.dumps(status))

