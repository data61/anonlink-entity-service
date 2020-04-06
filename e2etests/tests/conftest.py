import os
import time
import pytest
import requests as requests_library
import itertools
from e2etests.config import initial_delay
from e2etests.util import create_project_upload_fake_data, delete_project, create_project_no_data

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

    # Add an initial delay as well
    time.sleep(initial_delay)
    yield testing_session

# Parameterising on:
#
# - pairs of dataset sizes
# - overlap of the sizes
# - result_type for 2 parties in ['similarity_scores', 'permutations'] and for more parties in ['groups']
# - threshold

ENVVAR_NAME = 'ENTITY_SERVICE_RUN_SLOW_TESTS'
THRESHOLDS = [0.9, 1.0]
OVERLAPS = [0.0, 0.9]
ENCODING_SIZES = [8]
USES_BLOCKING = [True, False]
NUMBERS_PARTIES = [2, 3, 5]

if os.getenv(ENVVAR_NAME):
    ENCODING_SIZES.extend([64, 128, 512, 2048])
    OVERLAPS.extend([0.2, 0.5, 1.0])
    THRESHOLDS.extend([0.6, 0.8, 0.95])

FAST_SIZES_2P = tuple(itertools.product([1, 1000], repeat=2))
FAST_SIZES_NP = tuple(itertools.chain(
    FAST_SIZES_2P,
    [(1, 1000, 1000),
     (1000, 1, 1000),
     (1000, 1000, 1),
     (1000, 1000, 1000),
     (1000, 1000, 1000, 1000, 1000)]))

SLOW_SIZES_2P = tuple(itertools.combinations([1, 10000, 100000, 1000000], 2))
SLOW_SIZES_NP = tuple(itertools.chain(
    SLOW_SIZES_2P,
    itertools.product(
        [10000, 100000], [10000, 100000], [100000, 1000000]),
    ((10000, 10000, 100000, 100000, 1000000),)))

SIZES_2P = (tuple(itertools.chain(FAST_SIZES_2P, SLOW_SIZES_2P))
            if os.getenv(ENVVAR_NAME)
            else FAST_SIZES_2P)
SIZES_NP = (tuple(itertools.chain(FAST_SIZES_NP, SLOW_SIZES_NP))
            if os.getenv(ENVVAR_NAME)
            else FAST_SIZES_NP)

PROJECT_PARAMS_2P = tuple(
    itertools.product(SIZES_2P, OVERLAPS, ENCODING_SIZES))
PROJECT_PARAMS_NP = tuple(
    itertools.product(SIZES_NP, OVERLAPS, ENCODING_SIZES, USES_BLOCKING))
PROJECT_RESULT_TYPES_2P = ['similarity_scores', 'permutations']
PROJECT_RESULT_TYPES_NP = ['groups']


def create_project_response(requests, size, overlap, result_type, encoding_size=128, uses_blocking=False):
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
    project, dp_responses = create_project_upload_fake_data(
        requests, size, overlap=overlap, result_type=result_type, encoding_size=encoding_size)
    project.update({
        'size': size,
        'encoding-size': encoding_size,
        'upload-mode': 'JSON',
        'uses_blocking': uses_blocking,
        'overlap': overlap,
        'dp_responses': dp_responses
    })
    return project


@pytest.fixture(scope='function', params=PROJECT_PARAMS_2P)
def similarity_scores_project(request, requests):
    size, overlap, encoding_size = request.param
    prj = create_project_response(requests, size, overlap, 'similarity_scores', encoding_size)
    yield prj
    delete_project(requests, prj)


@pytest.fixture(scope='function', params=tuple(itertools.chain(
    [(t, 2) for t in PROJECT_RESULT_TYPES_2P],
    [(t, n) for t in PROJECT_RESULT_TYPES_NP for n in NUMBERS_PARTIES])))
def result_type_number_parties(request):
    yield request.param


@pytest.fixture(params=(
    *[(t, n) for t in PROJECT_RESULT_TYPES_2P
             for n in (None, 2)],
    *[(t, n) for t in PROJECT_RESULT_TYPES_NP
             for n in (None, *NUMBERS_PARTIES)]))
def result_type_number_parties_or_none(request):
    yield request.param


@pytest.fixture
def valid_project_params(request, result_type_number_parties_or_none):
    result_type, number_parties_or_none = result_type_number_parties_or_none
    # None is what we use to test handling of default values
    params_dict = {'result_type': result_type}
    if number_parties_or_none is not None:
        params_dict['number_parties'] = number_parties_or_none
    return params_dict

@pytest.fixture(scope='function')
def a_project(request, requests):
    project = create_project_no_data(
        requests,
        result_type="groups",
        number_parties=2)
    yield project
    # Release project resource
    delete_project(requests, project)


@pytest.fixture(scope='function')
def project(request, requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    project = create_project_no_data(
        requests,
        result_type=result_type,
        number_parties=number_parties)
    yield project
    # Release project resource
    delete_project(requests, project)


@pytest.fixture(scope='function', params=ENCODING_SIZES)
def encoding_size(request):
    yield request.param


@pytest.fixture(scope='function', params=THRESHOLDS)
def threshold(request):
    yield request.param


@pytest.fixture(scope='function', params=PROJECT_PARAMS_2P)
def permutations_project(request, requests):
    size, overlap, encoding_size = request.param
    prj = create_project_response(requests, size, overlap, 'permutations', encoding_size)
    yield prj
    delete_project(requests, prj)


@pytest.fixture(scope='function', params=PROJECT_PARAMS_NP)
def groups_project(request, requests):
    size, overlap, encoding_size, uses_blocking = request.param
    prj = create_project_response(requests, size, overlap, 'groups', encoding_size, uses_blocking)
    yield prj
    delete_project(requests, prj)


@pytest.fixture(
    params=itertools.chain(
        itertools.product(PROJECT_RESULT_TYPES_2P, [1, 3, 4, 5]),
        [(t, 1) for t in PROJECT_RESULT_TYPES_NP]))
def invalid_result_type_number_parties(request):
    yield request.param
