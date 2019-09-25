import redis
from redis.sentinel import Sentinel
import structlog

from entityservice.settings import Config as config

logger = structlog.get_logger()
redis_host = config.REDIS_SERVER
redis_pass = config.REDIS_PASSWORD
redis_port = 26379


def connect_to_redis(read_only=False):
    """
    Get a connection to the master redis service.

    """
    logger.debug("Connecting to redis", server=redis_host, port=redis_port)
    if config.REDIS_USE_SENTINEL:
        sentinel = Sentinel([(redis_host, )], password=redis_pass, socket_timeout=5)
        if read_only:
            logger.debug("Looking up read only redis slave using sentinel protocol")
            r = sentinel.slave_for('mymaster')
        else:
            logger.debug("Looking up redis master using sentinel protocol")
            r = sentinel.master_for('mymaster')
    else:
        r = redis.StrictRedis(host=redis_host, password=redis_pass)
    return r
