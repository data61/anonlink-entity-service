import time
import pytest
import requests as requests_library

from entityservice.tests.util import create_project_upload_fake_data

THROTTLE_SLEEP = 0.1
DEFAULT_OVERLAPS = [0.2, 0.3, 0.5, 0.6, 0.8, 0.9]
DEFAULT_SIZES = [(100, 100), (100, 1000), (1000, 100), (1000, 1000)]


@pytest.fixture(scope='session')
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


def create_project_response(requests, overlap, size, result_type):
    new_project_response, dp_1, dp_2 = create_project_upload_fake_data(
        requests, size, overlap=overlap, result_type=result_type)
    new_project_response.update({
        'size': size,
        'overlap': overlap,
        'dp_1': dp_1,
        'dp_2': dp_2
    })
    return new_project_response


def project_creation_generator(requests, result_type, overlaps=DEFAULT_OVERLAPS, sizes=DEFAULT_SIZES):
    return (create_project_response(requests, overlap, size, result_type)
            for overlap in overlaps
            for size in sizes)


@pytest.fixture
def example_mapping_projects(requests):
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
    yield project_creation_generator(requests, 'mapping')


@pytest.fixture
def example_similarity_projects(requests):
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
    yield project_creation_generator(requests, 'similarity_scores')


@pytest.fixture
def example_permutation_projects(requests):
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
    yield project_creation_generator(requests, 'permutation_unencrypted_mask')
