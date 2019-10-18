import pickle
import structlog

from entityservice.cache.connection import connect_to_redis

logger = structlog.get_logger()


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
