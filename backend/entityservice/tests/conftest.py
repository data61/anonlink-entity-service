import time
import pytest
import requests as requests_library
THROTTLE_SLEEP = 0.1


@pytest.fixture
def requests():
    """
    We inject the requests library so that we could potentially monkey patch it
    For now we just add a small sleep to ensure we don't get throttled when
    tests run back to back.
    """
    yield requests_library
    time.sleep(THROTTLE_SLEEP)
