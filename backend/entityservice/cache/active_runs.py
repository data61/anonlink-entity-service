"""
Cache information about the run state in redis.

Note across the cache we use a common redis hash for each run,
this module uses the 'state' key.

See https://redis.io/commands#hash
"""
from enum import Enum
import structlog

from entityservice.settings import Config as config
from entityservice.cache.connection import connect_to_redis
from entityservice.cache.helpers import _get_run_hash_key

logger = structlog.get_logger()


class RunState(Enum):
    """
    A run state is stored in the cache to provide a fast method of
    differentiating between an active, completed, or deleted run.

    An unlikely option of ``MISSING`` will occur if there is
    no corresponding entry in redis for a ``run_id``. Note redis
    returns ``None`` hence the value in this Enum.
    """
    MISSING = None
    ACTIVE = b'active'
    COMPLETE = b'complete'
    DELETED = b'deleted'


def _set_run_state(run_id, state):
    logger.debug(f"Setting run state to '{state.name}'", run_id=run_id)
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    res = r.hset(key, 'state', state.value)
    r.expire(key, config.CACHE_EXPIRY)
    return res


def _get_run_state(run_id):
    r = connect_to_redis(read_only=True)
    key = _get_run_hash_key(run_id)
    # hget returns None if missing key/name, and bytes if present
    maybe_state = r.hget(key, 'state')
    logger.debug("Loaded run state from cache", run_id=run_id, state=maybe_state)
    return RunState(maybe_state)


def set_run_state_deleted(run_id):
    return _set_run_state(run_id, state=RunState.DELETED)


def set_run_state_active(run_id):
    return _set_run_state(run_id, state=RunState.ACTIVE)


def set_run_state_complete(run_id):
    return _set_run_state(run_id, state=RunState.COMPLETE)


def is_run_active(run_id):
    return RunState.ACTIVE == _get_run_state(run_id)


def is_run_missing(run_id):
    return RunState.MISSING == _get_run_state(run_id)


def clear_run_state(run_id):
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    r.hdel(key, 'state')
