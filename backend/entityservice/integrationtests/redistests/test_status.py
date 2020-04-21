import time

from entityservice.cache import connect_to_redis, get_status, set_status


class TestStatus:

    def _get_redis_rw(self):
        return connect_to_redis()

    def test_get_missing_status(self):
        r = self._get_redis_rw()
        r.delete('entityservice-status')
        status = get_status()
        assert status is None


    def test_set_status(self):
        original_status = get_status()
        if original_status is None:
            new_status = {}
        else:
            new_status = original_status

        new_status['testkey'] = 'testvalue'
        set_status(new_status)
        time.sleep(0.2)
        updated_status = get_status()
        assert 'testkey' in updated_status
        set_status(original_status)

