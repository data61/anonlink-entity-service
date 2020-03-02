import datetime
import time

import pytest
import redis

from entityservice.settings import Config as config
from entityservice.cache import connect_to_redis, clear_progress, save_current_progress, get_progress


class TestProgress:

    def _get_redis_rw(self):
        return connect_to_redis()

    def test_clear_missing_progress(self):
        clear_progress('test_clear_missing_progress')

    def test_clear_progress(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'runtest_clear_progress'
        save_current_progress(1, runid, config)
        assert 1 == get_progress(runid)
        clear_progress(runid)
        assert get_progress(runid) is None

    def test_storing_wrong_type(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'test_storing_wrong_type'
        with pytest.raises(redis.exceptions.ResponseError):
            save_current_progress(1.5, runid, config)

    def test_progress_expires(self):
        # Uses the minimum expiry of 1 second
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'test_progress_expires'
        save_current_progress(42, runid, config)
        cached_progress = get_progress(runid)
        assert cached_progress == 42
        time.sleep(1)
        # After expiry the progress should be reset to None
        assert get_progress(runid) is None

    def test_progress_increments(self):
        config.CACHE_EXPIRY = datetime.timedelta(seconds=1)
        runid = 'test_progress_increments'
        save_current_progress(1, runid, config)
        cached_progress = get_progress(runid)
        assert cached_progress == 1
        for i in range(99):
            save_current_progress(1, runid, config)

        assert 100 == get_progress(runid)