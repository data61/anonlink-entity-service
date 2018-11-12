import os
import time
import pytest
import requests as requests_library
import itertools

from entityservice.tests.util import create_project_upload_fake_data, delete_project, temporary_blank_project, \
    create_project_no_data

THROTTLE_SLEEP = 0.2


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


# Parameterising on:
#
# - pairs of dataset sizes
# - overlap of the sizes
# - result_type in ['mapping', 'similarity_scores', 'permutations']
# - threshold

ENVVAR_NAME = 'ENTITY_SERVICE_RUN_SLOW_TESTS'
THRESHOLDS = [0.9, 1.0]
OVERLAPS = [0.0, 0.9, 1.0]
ENCODING_SIZES = [8]

if os.getenv(ENVVAR_NAME):
    ENCODING_SIZES.extend([64, 128, 512, 2048])
    OVERLAPS.extend([0.2, 0.5])
    THRESHOLDS.extend([0.6, 0.8, 0.95])

SIZES = itertools.chain(
    # Default project sizes
    itertools.product([1, 100, 1000], repeat=2),
    # Large project sizes; will only run if the environment variable is set
    () if not os.getenv(ENVVAR_NAME)
       else itertools.combinations([1, 10000, 100000, 1000000], 2))

PROJECT_PARAMS = list(itertools.product(SIZES, OVERLAPS, ENCODING_SIZES))
PROJECT_RESULT_TYPES = ['mapping', 'similarity_scores', 'permutations']


def create_project_response(requests, size, overlap, result_type, encoding_size=128):
    """
    Create a project with the given size, overlap and result_type.

    Tests that use one of these projects will get a dict like the following:

    {
        "project_id": "ID",
        "upload-mode": "BINARY" | "JSON",
        "size": [size 1, size 2],
        "encoding-size": int number of bytes in each encoding e.g. 128,
        "overlap": float between 0 and 1,
        "result_token": "TOKEN",
        "upload_tokens": [TOKENS, ...],
        "dp_1": <JSON RESPONSE TO DATA UPLOAD>
        "dp_2": <JSON RESPONSE TO DATA UPLOAD>
    }
    """
    project, dp_1, dp_2 = create_project_upload_fake_data(
        requests, size, overlap=overlap, result_type=result_type, encoding_size=encoding_size)
    project.update({
        'size': size,
        'encoding-size': encoding_size,
        'upload-mode': 'JSON',
        'overlap': overlap,
        'dp_1': dp_1,
        'dp_2': dp_2
    })
    return project


@pytest.fixture(scope='function', params=PROJECT_PARAMS)
def mapping_project(request, requests):
    size, overlap, encoding_size = request.param
    prj = create_project_response(requests, size, overlap, 'mapping', encoding_size)
    yield prj
    delete_project(requests, prj)


@pytest.fixture(scope='function', params=PROJECT_PARAMS)
def similarity_scores_project(request, requests):
    size, overlap, encoding_size = request.param
    prj = create_project_response(requests, size, overlap, 'similarity_scores', encoding_size)
    yield prj
    delete_project(requests, prj)


@pytest.fixture(scope='function', params=PROJECT_RESULT_TYPES)
def result_type(request):
    yield request.param


@pytest.fixture(scope='function', params=PROJECT_RESULT_TYPES)
def project(request, requests):
    result_type = request.param
    project = create_project_no_data(requests, result_type)
    try:
        yield project
    finally:
        # Release project resource
        delete_project(requests, project)


@pytest.fixture(scope='function', params=ENCODING_SIZES)
def encoding_size(request):
    yield request.param


@pytest.fixture(scope='function', params=THRESHOLDS)
def threshold(request):
    yield request.param


@pytest.fixture(scope='function', params=PROJECT_PARAMS)
def permutations_project(request, requests):
    size, overlap, encoding_size = request.param
    prj = create_project_response(requests, size, overlap, 'permutations', encoding_size)
    yield prj
    delete_project(requests, prj)
