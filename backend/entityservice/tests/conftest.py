import time
import pytest
import requests as requests_library

from entityservice.tests.util import create_project_upload_fake_data

THROTTLE_SLEEP = 0.1


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


@pytest.fixture
def example_mapping_projects(requests):
    """
    A fixture that injects an iterator of example projects of result_type="mapping" with various
    overlaps and sizes.

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
    def project_creation_generator():
        for overlap in [0.3, 0.5, 0.6, 0.8, 0.9]:
            for size in [(100,100), (100, 1000), (1000, 100), (1000, 1000)]:
                new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, size, overlap=overlap)
                new_project_response['size'] = size
                new_project_response['overlap'] = overlap
                new_project_response['dp_1'] = dp1
                new_project_response['dp_2'] = dp2
                yield new_project_response

    yield project_creation_generator()


@pytest.fixture
def example_similarity_projects(requests):
    """
    A fixture that injects an iterator of example projects of result_type="permutation" with various
    overlaps and sizes.

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
    def project_creation_generator():
        for overlap in [0.2, 0.5, 0.9]:
            for size in [(100, 1000), (1000, 100), (1000, 1000)]:
                new_project_response, dp1, dp2 = create_project_upload_fake_data(
                    requests,
                    size,
                    overlap=overlap,
                    result_type='similarity_scores')
                new_project_response['size'] = size
                new_project_response['overlap'] = overlap
                new_project_response['dp_1'] = dp1
                new_project_response['dp_2'] = dp2
                yield new_project_response

    yield project_creation_generator()
