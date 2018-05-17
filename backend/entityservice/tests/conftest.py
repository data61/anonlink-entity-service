import time
import pytest
import requests as requests_library
import itertools

from entityservice.tests.util import create_project_upload_fake_data

THROTTLE_SLEEP = 0.1
DEFAULT_OVERLAPS = [0.2, 0.5, 0.9]
# NB: For some reason these things have to be actual lists rather than
# generators, otherwise pytest won't generate the fixtures below
# correctly (yes, this is the case even though the fixtures themselves
# are still parameterised by generators -- go figure).
DEFAULT_SIZES = list(itertools.product([100, 1000], repeat = 2))
LONG_TEST_SIZES = list(itertools.product([10000, 100000, 1000000], repeat = 2))


@pytest.fixture(scope='session')
def requests():
    """
    We inject the requests session.
    For now we just add a small sleep after every request to ensure we don't get throttled when
    tests run back to back. Note the rate limit in nginx is 10 requests per ip per second.
    """
    def delay_next(r, *args, **kwargs):
        time.sleep(THROTTLE_SLEEP)

    testing_session = requests_library.Session()
    testing_session.hooks['response'].append(delay_next)
    yield testing_session


def create_project_response(requests, size, overlap, result_type):
    project, dp_1, dp_2 = create_project_upload_fake_data(
        requests, size, overlap=overlap, result_type=result_type)
    project.update({
        'size': size,
        'overlap': overlap,
        'dp_1': dp_1,
        'dp_2': dp_2
    })
    return project


@pytest.fixture(params = itertools.product(DEFAULT_SIZES, DEFAULT_OVERLAPS + [0.3, 0.6, 0.8]))
def example_mapping_projects(requests, request):
    """
    A fixture that injects an iterator of example projects of
    result_type="mapping" with various overlaps and sizes.

    Tests that use this fixture will get a list of dicts like the following:

    {
        "project_id": "ID",
        "size": [size 1, size2],
        "overlap": float,
        "result_token": "TOKEN",
        "upload_tokens": [TOKENS, ...],
        "dp_1": <JSON RESPONSE TO DATA UPLOAD>
        "dp_2": <JSON RESPONSE TO DATA UPLOAD>
    }

    """
    size, overlap = request.param
    yield create_project_response(requests, size, overlap, 'mapping')


@pytest.fixture(params = itertools.product(DEFAULT_SIZES, DEFAULT_OVERLAPS))
def example_similarity_projects(requests, request):
    """
    A fixture that injects an iterator of example projects of
    result_type="similarity_score" with various overlaps and sizes.

    Tests that use this fixture will get a list of dicts like the following:

    {
        "project_id": "ID",
        "size": [size 1, size2],
        "overlap": float,
        "result_token": "TOKEN",
        "upload_tokens": [TOKENS, ...],
        "dp_1": <JSON RESPONSE TO DATA UPLOAD>
        "dp_2": <JSON RESPONSE TO DATA UPLOAD>
    }

    """
    size, overlap = request.param
    yield create_project_response(requests, size, overlap, 'similarity_scores')


@pytest.fixture(params = itertools.product(DEFAULT_SIZES, DEFAULT_OVERLAPS))
def example_permutation_projects(requests, request):
    """
    A fixture that injects an iterator of example projects of
    result_type="permutation_unencrypted_mask" with various overlaps
    and sizes.

    Tests that use this fixture will get a list of dicts like the following:

    {
        "project_id": "ID",
        "size": [size 1, size2],
        "overlap": float,
        "result_token": "TOKEN",
        "upload_tokens": [TOKENS, ...],
        "dp_1": <JSON RESPONSE TO DATA UPLOAD>
        "dp_2": <JSON RESPONSE TO DATA UPLOAD>
    }

    """
    size, overlap = request.param
    yield create_project_response(requests, size, overlap, 'permutation_unencrypted_mask')
