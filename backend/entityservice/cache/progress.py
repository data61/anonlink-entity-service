import structlog

from entityservice.cache.connection import connect_to_redis

logger = structlog.get_logger()


def save_current_progress(comparisons, run_id):
    logger.debug(f"Updating progress. Compared {comparisons} CLKS", run_id=run_id)
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
