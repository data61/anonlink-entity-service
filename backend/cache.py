import redis

import pickle
import logging

import serialization
import database


logger = logging.getLogger('cache')


def set_deserialized_filter(dp_id, python_filters):
    logger.debug("Pickling filters and storing in redis")
    key = 'clk-pkl-{}'.format(dp_id)
    r = redis.StrictRedis(host='redis', port=6379, db=0)
    pickled_filters = pickle.dumps(python_filters)
    r.set(key, pickled_filters)


def get_deserialized_filter(dp_id):
    """Cached, deserialized version.
    """
    logger.debug("Getting filters")
    key = 'clk-pkl-{}'.format(dp_id)
    r = redis.StrictRedis(host='redis', port=6379, db=0)

    # Check if this dp_id is already saved in redis?
    if r.exists(key):
        logger.debug("returning filters from cache")
        return pickle.loads(r.get(key))
    else:
        logger.debug("Getting filters from db")
        db = database.connect_db()
        json_serialized_filters, popcnts = database.get_filter(db, dp_id)
        logger.debug("Deserialising from JSON")

        python_filters = []
        for i, (f, cnt) in enumerate(zip(json_serialized_filters, popcnts)):
            ba = serialization.deserialize_bitarray(f)
            python_filters.append((ba, i, cnt))

        set_deserialized_filter(dp_id, python_filters)
        return python_filters


def remove_from_cache(dp_id):
    logger.debug("Deleting from redis cache")
    r = redis.StrictRedis(host='redis', port=6379, db=0)
    key = 'clk-pkl-{}'.format(dp_id)
    r.delete(key)


def update_progress(comparisons, resource_id):
    r = redis.StrictRedis(host='redis', port=6379, db=0)
    key = 'progress-{}'.format(resource_id)
    r.incr(key, comparisons)


def get_progress(resource_id):
    r = redis.StrictRedis(host='redis', port=6379, db=0)
    key = 'progress-{}'.format(resource_id)
    res = r.get(key)
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return 0
