import structlog

from entityservice.cache.connection import connect_to_redis
from entityservice.cache.helpers import _get_run_hash_key

logger = structlog.get_logger()


def set_run_state(run_id, state='active'):
    logger.info("Setting run active", run_id=run_id)
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    r.hset(key, 'state', state)


def get_run_state(run_id):
    r = connect_to_redis(read_only=True)
    logger.info("Getting run state", run_id=run_id)
    key = _get_run_hash_key(run_id)
    return r.hget(key, 'state')


def is_run_active(run_id):
    return 'active' == get_run_state(run_id)

