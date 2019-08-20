import redis
from redis.sentinel import Sentinel

import pickle

import structlog

from entityservice import serialization
from entityservice import database
from entityservice.database import logger, DBConn
from entityservice.object_store import connect_to_object_store
from entityservice.settings import Config as config

logger = structlog.get_logger()
redis_host = config.REDIS_SERVER
redis_pass = config.REDIS_PASSWORD


def connect_to_redis(read_only=False):
    """
    Get a connection to the master redis service.

    """
    logger.debug("Connecting to redis")
    if config.REDIS_USE_SENTINEL:
        sentinel = Sentinel([(redis_host, 26379)], password=redis_pass, socket_timeout=5)
        if read_only:
            logger.debug("Looking up read only redis slave using sentinel protocol")
            r = sentinel.slave_for('mymaster')
        else:
            logger.debug("Looking up redis master using sentinel protocol")
            r = sentinel.master_for('mymaster')
    else:
        r = redis.StrictRedis(host=redis_host, password=redis_pass)
    return r


def set_deserialized_filter(dp_id, python_filters):
    if len(python_filters) <= config.MAX_CACHE_SIZE:
        logger.debug("Pickling filters and storing in redis")
        key = 'clk-pkl-{}'.format(dp_id)
        pickled_filters = pickle.dumps(python_filters)
        r = connect_to_redis()
        r.set(key, pickled_filters)
    else:
        logger.info("Skipping storing filters in redis cache due to size")


def get_deserialized_filter(dp_id):
    """Cached, deserialized version.
    """
    logger.debug("Getting filters")
    key = 'clk-pkl-{}'.format(dp_id)
    r = connect_to_redis(read_only=True)

    # Check if this dp_id is already saved in redis?
    if r.exists(key):
        logger.debug("returning filters from cache")
        return pickle.loads(r.get(key))
    else:
        logger.debug("Looking up popcounts and filename from database")
        with DBConn() as db:
            #db = database.connect_db()
            mc = connect_to_object_store()
            serialized_filters_file = database.get_filter_metadata(db, dp_id)

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


def update_progress(comparisons, run_id):
    r = connect_to_redis()
    key = 'progress-{}'.format(run_id)
    r.incr(key, comparisons)


def get_progress(run_id):
    r = connect_to_redis(read_only=True)
    key = 'progress-{}'.format(run_id)
    res = r.get(key)
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return None


def clear_progress(run_id):
    r = connect_to_redis()
    key = 'progress-{}'.format(run_id)
    r.delete(key)


def get_status():
    r = connect_to_redis(read_only=True)
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


def save_current_progress(comparisons, run_id):
    logger.debug(f"Progress. Compared {comparisons} CLKS", run_id=run_id)
    update_progress(comparisons, run_id)
