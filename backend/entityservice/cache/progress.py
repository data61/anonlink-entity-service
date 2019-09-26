import structlog

from entityservice.settings import Config as config
from entityservice.cache.connection import connect_to_redis
from entityservice.cache.helpers import _get_run_hash_key

logger = structlog.get_logger()


def save_current_progress(comparisons, run_id):
    logger.debug(f"Updating progress. Compared {comparisons} CLKS", run_id=run_id)
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    r.hincrby(key, 'progress', comparisons)
    r.expire(key, config.CACHE_EXPIRY)


def get_progress(run_id):
    r = connect_to_redis(read_only=True)
    key = _get_run_hash_key(run_id)
    res = r.hget(key, 'progress')
    # redis returns bytes, and None if not present
    if res is not None:
        return int(res)
    else:
        return None


def clear_progress(run_id):
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    r.hdel(key, 'progress')
