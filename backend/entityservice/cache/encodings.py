import pickle
import structlog

from entityservice.object_store import connect_to_object_store
from entityservice.serialization import binary_unpack_filters
from entityservice.cache.connection import connect_to_redis
from entityservice.database import DBConn, get_filter_metadata
from entityservice.settings import Config as config

logger = structlog.get_logger()


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
            serialized_filters_file, encoding_size = get_filter_metadata(db, dp_id)
        mc = connect_to_object_store()
        logger.debug("Getting filters from object store")

        # Note this uses already calculated popcounts unlike
        # serialization.deserialize_filters()
        raw_data_response = mc.get_object(config.MINIO_BUCKET, serialized_filters_file)
        python_filters = binary_unpack_filters(raw_data_response.stream(encoding_size))

        set_deserialized_filter(dp_id, python_filters)
        return python_filters


def remove_from_cache(dp_id):
    logger.debug("Deleting CLKS for DP {} from redis cache".format(dp_id))
    r = connect_to_redis()
    key = 'clk-pkl-{}'.format(dp_id)
    r.delete(key)
