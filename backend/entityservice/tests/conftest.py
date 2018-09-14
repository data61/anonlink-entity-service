import time
import pytest
import requests as requests_library
import itertools

from entityservice.tests.util import create_project_upload_fake_data

THROTTLE_SLEEP = 0.1

# Parameterising on:
#
# - pairs of dataset sizes
# - overlap of the sizes
# - result_type in ['mapping', 'similarity_scores', 'permutations']
#
# - threshold

# Available project fixture names are determined by RESULT_TYPES:
#
#  [rt + '_project' for rt in RESULT_TYPES]
#
RESULT_TYPES = ['mapping', 'similarity_scores', 'permutations']

# The globals {QUICK,DEFAULT,LONG}_{SIZES,OVERLAPS} are used to
# control the parameterisation of the fixtures below via the command
# line.
QUICK_OVERLAPS = [0.0, 0.6, 1.0]
DEFAULT_OVERLAPS = QUICK_OVERLAPS + [0.2, 0.9]

THRESHOLDS = [0.6, 0.9, 0.99]

# NB: For some reason these things have to be actual lists rather than
# generators, otherwise pytest won't generate the fixtures below
# correctly (yes, this is the case even though the fixtures themselves
# can be parameterised by generators -- go figure).
QUICK_SIZES = list(itertools.combinations([1, 1000, 100], 2))
DEFAULT_SIZES = list(itertools.product([1, 100, 1000], repeat=2))
LONG_TEST_SIZES = list(
    itertools.chain(
        DEFAULT_SIZES,
        itertools.combinations([1, 10000, 100000, 1000000], 2)))


def pytest_addoption(parser):
    quickhelptxt = 'run a small selection of tests from the default suite'
    parser.addoption('--quick', action='store_true', default=False, help=quickhelptxt)

    longhelptxt = 'run the default tests along with some tests on very large input'
    parser.addoption('--long', action='store_true', default=False, help=longhelptxt)


def create_project_response(requests, size, overlap, result_type):
    """
    Create a project with the given size, overlap and result_type.

    Tests that use one of these projects will get a dict like the following:

    {
        "project_id": "ID",
        "size": [size 1, size 2],
        "overlap": float between 0 and 1,
        "result_token": "TOKEN",
        "upload_tokens": [TOKENS, ...],
        "dp_1": <JSON RESPONSE TO DATA UPLOAD>
        "dp_2": <JSON RESPONSE TO DATA UPLOAD>
    }
    """
    project, dp_1, dp_2 = create_project_upload_fake_data(
        requests, size, overlap=overlap, result_type=result_type)
    project.update({
        'size': size,
        'overlap': overlap,
        'dp_1': dp_1,
        'dp_2': dp_2
    })
    return project


def create_projects(result_type, sizes, overlaps):
    rq = next(requests())
    projects = []
    params = list(itertools.product(sizes, overlaps))
    print("Generating {} '{}' projects ".format(len(params), result_type), end='', flush=True)
    for size, overlap in params:
        projects.append(create_project_response(rq, size, overlap, result_type))
        time.sleep(THROTTLE_SLEEP)
        print('.', end='', flush=True)
    print()
    return projects


def pytest_generate_tests(metafunc):
    """
    This is a special pytest magic function that provides a hook at
    the point before test execution.  We can use this to parameterise
    the project fixtures.  This code is informed by

      https://docs.pytest.org/en/latest/example/parametrize.html  (top)
      https://docs.pytest.org/en/latest/fixture.html#fixture-parametrize
    """
    # Select TEST_SIZES and TEST_OVERLAPS according to whether we've
    # been asked to do quick tests, long tests, or just the
    # defaults. If both --quick and --long are specified, then --long
    # wins.
    sizes = DEFAULT_SIZES
    overlaps = DEFAULT_OVERLAPS
    if metafunc.config.getoption('quick'):
        sizes = QUICK_SIZES
        overlaps = QUICK_OVERLAPS
    if metafunc.config.getoption('long'):
        sizes = LONG_TEST_SIZES
        overlaps = DEFAULT_OVERLAPS

    for rt in RESULT_TYPES:
        fixture_name = rt + '_project'
        if fixture_name in metafunc.fixturenames:
            metafunc.parametrize(fixture_name, create_projects(rt, sizes, overlaps))

    if 'threshold' in metafunc.fixturenames:
        metafunc.parametrize('threshold', THRESHOLDS)


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
