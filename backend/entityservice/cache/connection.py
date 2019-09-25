import redis
from redis.sentinel import Sentinel
import structlog

from entityservice.settings import Config as config

logger = structlog.get_logger()
redis_host = config.REDIS_SERVER
redis_pass = config.REDIS_PASSWORD
redis_sentinel_port = 26379


def connect_to_redis(read_only=False):
    """
    Get a connection to the master redis service.

    """
    logger.debug("Connecting to redis", server=redis_host, port=redis_sentinel_port)
    if config.REDIS_USE_SENTINEL:
        sentinel_service = Sentinel([(redis_host, redis_sentinel_port)], password=redis_pass, socket_timeout=5)
        sentinel_name = config.REDIS_SENTINEL_NAME
        if read_only:
            logger.debug("Looking up read only redis slave using sentinel protocol")
            r = sentinel_service.slave_for(sentinel_name)
        else:
            logger.debug("Looking up redis master using sentinel protocol")
            r = sentinel_service.master_for(sentinel_name)
    else:
        r = redis.StrictRedis(host=redis_host, password=redis_pass)
    return r
