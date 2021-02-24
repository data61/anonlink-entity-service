import datetime
import time

import pytest
import redis

from entityservice.settings import Config as config
from entityservice.cache import connect_to_redis, clear_progress, get_candidate_count_for_run, save_current_progress, \
    get_comparison_count_for_run


class TestProgress:

    def _get_redis_rw(self):
        return connect_to_redis()

    def test_clear_missing_progress(self):
        clear_progress('test_clear_missing_progress')

    def test_clear_progress(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'runtest_clear_progress'
        save_current_progress(1, 1, runid, config)
        assert 1 == get_comparison_count_for_run(runid)
        assert 1 == get_candidate_count_for_run(runid)
        clear_progress(runid)
        assert get_comparison_count_for_run(runid) is None
        assert get_candidate_count_for_run(runid) is None

    def test_storing_wrong_type(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'test_storing_wrong_type'
        with pytest.raises(redis.exceptions.ResponseError):
            save_current_progress(1.5, 1, runid, config)
        with pytest.raises(redis.exceptions.ResponseError):
            save_current_progress(1, 1.5, runid, config)

    def test_progress_expires(self):
        # Uses the minimum expiry of 1 second
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'test_progress_expires'
        save_current_progress(42, 7, runid, config)
        cached_progress = get_comparison_count_for_run(runid)
        assert cached_progress == 42
        time.sleep(1)
        # After expiry the progress should be reset to None
        assert get_comparison_count_for_run(runid) is None
        assert get_candidate_count_for_run(runid) is None

    def test_progress_increments(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=5)
        runid = 'test_progress_increments'
        save_current_progress(2, 1, runid, config)
        assert get_comparison_count_for_run(runid) == 2
        for i in range(99):
            save_current_progress(2, 1, runid, config)

        assert 200 == get_comparison_count_for_run(runid)
        assert 100 == get_candidate_count_for_run(runid)
