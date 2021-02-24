import structlog

from entityservice.settings import Config as globalconfig
from entityservice.cache.connection import connect_to_redis
from entityservice.cache.helpers import _get_run_hash_key, _get_project_hash_key, _convert_redis_result_to_int
import entityservice.database as db

logger = structlog.get_logger()


def get_total_number_of_comparisons(project_id):
    r = connect_to_redis(read_only=True)
    key = _get_project_hash_key(project_id)
    res = r.hget(key, 'total_comparisons')
    # hget returns None if missing key/name, and bytes if present
    if res:
        return _convert_redis_result_to_int(res)
    else:
        # Calculate the number of comparisons
        with db.DBConn() as conn:
            total_comparisons = db.get_total_comparisons_for_project(conn, project_id)
        # get a writable connection to redis
        r = connect_to_redis()
        res = r.hset(key, 'total_comparisons', total_comparisons)
        r.expire(key, 60*60)
        return total_comparisons


def save_current_progress(comparisons, candidate_pairs, run_id, config=None):
    """
    Record progress for a run in the redis cache, adding the number of candidates identified
    from the number of comparisons carried out.

    This is safe to call from concurrent processes.

    :param int comparisons: The number of pairwise comparisons that have been computed for this update.
    :param int candidate_pairs: Number of candidates, edge count where the similarity was above
        the configured threshold.
    """
    if config is None:
        config = globalconfig
    logger.debug(f"Updating progress. Compared {comparisons} CLKS", run_id=run_id)
    if comparisons > 0:
        r = connect_to_redis()
        key = _get_run_hash_key(run_id)
        r.hincrby(key, 'comparisons', comparisons)
        r.hincrby(key, 'candidates', candidate_pairs)
        r.expire(key, config.CACHE_EXPIRY)


def get_comparison_count_for_run(run_id):
    r = connect_to_redis(read_only=True)
    key = _get_run_hash_key(run_id)
    res = r.hget(key, 'comparisons')
    return _convert_redis_result_to_int(res)


def get_candidate_count_for_run(run_id):
    r = connect_to_redis(read_only=True)
    key = _get_run_hash_key(run_id)
    res = r.hget(key, 'candidates')
    return _convert_redis_result_to_int(res)


def clear_progress(run_id):
    r = connect_to_redis()
    key = _get_run_hash_key(run_id)
    r.hdel(key, 'comparisons')
    r.hdel(key, 'candidates')
