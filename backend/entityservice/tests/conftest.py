import time
import pytest
import requests as requests_library

THROTTLE_SLEEP = 0.1


@pytest.fixture
def requests():
    """
    We inject the requests session.
    For now we just add a small sleep after every request to ensure we don't get throttled when
    tests run back to back. Note the rate limit in nginx is 10 requests per ip per second.
    """

    testing_session = requests_library.Session()

    def delay_next(r, *args, **kwargs):
        time.sleep(THROTTLE_SLEEP)

    testing_session.hooks['response'].append(delay_next)

    yield testing_session
