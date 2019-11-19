import base64
import datetime
import itertools
import math
import os
import random
import time
from contextlib import contextmanager
from enum import IntEnum

from bitarray import bitarray
import iso8601

from entityservice.tests.config import url


def serialize_bytes(hash_bytes):
    """ Serialize bloomfilter bytes

    """
    return base64.b64encode(hash_bytes).decode()


def serialize_filters(filters):
    """Serialize filters as clients are required to."""
    return [
        serialize_bytes(f) for f in filters
    ]


def generate_bytes(length):
    return random.getrandbits(length * 8).to_bytes(length, 'big')


def generate_clks(count, size):
    """Generate random clks of given size.

    :param count: The number of clks to generate
    :param size: The number of bytes per generated clk.
    """
    res = []
    for i in range(count):
        hash_bytes = generate_bytes(size)
        res.append(hash_bytes)
    return res


def generate_json_serialized_clks(count, size=128):
    clks = generate_clks(count, size)
    return [serialize_bytes(hash_bytes) for hash_bytes in clks]


def nonempty_powerset(iterable):
    "nonempty_powerset([1,2,3]) --> (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
    # Inspired by:
    # https://docs.python.org/3/library/itertools.html#itertools-recipes
    s = tuple(iterable)
    return itertools.chain.from_iterable(
        itertools.combinations(s, r) for r in range(1, len(s)+1))


def generate_overlapping_clk_data(
    dataset_sizes, overlap=0.9, encoding_size=128, seed=666):
    """Generate random datsets with fixed overlap.

    Postcondition:
    for all some_datasets in nonempty_powerset(datasets),
    len(set.intersection(*some_datasets)) 
        == floor(min(map(len, some_datasets))
           * overlap ** (len(some_datasets) - 1))
    (in case of two datasets A and V this reduces to:
     len(A & B) = floor(min(len(A), len(B)) * overlap)

    For some sets of parameters (particularly when dataset_sizes is
    long), meeting this postcondition is impossible. In that case, we
    raise ValueError.
    """
    i = 0
    datasets_n = len(dataset_sizes)
    dataset_record_is = tuple(set() for _ in dataset_sizes)
    for overlapping_n in range(datasets_n, 0, -1):
        for overlapping_datasets in itertools.combinations(
                range(datasets_n), overlapping_n):
            records_n = int(overlap ** (len(overlapping_datasets) - 1)
                            * min(map(dataset_sizes.__getitem__,
                                      overlapping_datasets)))
            current_records_n = len(set.intersection(
                *map(dataset_record_is.__getitem__, overlapping_datasets)))
            if records_n < current_records_n:
                raise ValueError(
                    'parameters make meeting postcondition impossible')
            for j in overlapping_datasets:
                dataset_record_is[j].update(
                    range(i, i + records_n - current_records_n))
            i += records_n - current_records_n

    # Sanity check
    if __debug__:
        for dataset, dataset_size in zip(dataset_record_is, dataset_sizes):
            assert len(dataset) == dataset_size
        for datasets_with_size in nonempty_powerset(
                zip(dataset_record_is, dataset_sizes)):
            some_datasets, sizes = zip(*datasets_with_size)
            intersection = set.intersection(*some_datasets)
            aim_size = int(min(sizes)
                           * overlap ** (len(datasets_with_size) - 1))
            assert len(intersection) == aim_size

    records = generate_json_serialized_clks(i, size=encoding_size)
    datasets = tuple(list(map(records.__getitem__, record_is))
                     for record_is in dataset_record_is)
    
    rng = random.Random(seed)
    for dataset in datasets:
        rng.shuffle(dataset)

    return datasets


def get_project_description(requests, new_project_data):
    project_description_response = requests.get(url + '/projects/{}'.format(new_project_data['project_id']),
                            headers={'Authorization': new_project_data['result_token']})

    assert project_description_response.status_code == 200
    return project_description_response.json()


def create_project_no_data(requests,
                           result_type='groups', number_parties=None):
    number_parties_param = (
        {} if number_parties is None else {'number_parties': number_parties})
    new_project_response = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         'result_type': result_type,
                                         **number_parties_param
                                     })
    assert new_project_response.status_code == 201, 'I received this instead: {}'.format(new_project_response.text)
    return new_project_response.json()


@contextmanager
def temporary_blank_project(requests, result_type='groups'):
    # Code to acquire resource, e.g.:
    project = create_project_no_data(requests, result_type)
    yield project
    # Release project resource
    delete_project(requests, project)


def create_project_upload_fake_data(
        requests,
        sizes, overlap=0.75,
        result_type='groups', encoding_size=128):
    data = generate_overlapping_clk_data(
        sizes, overlap=overlap, encoding_size=encoding_size)
    new_project_data, json_responses = create_project_upload_data(
        requests, data, result_type=result_type)
    assert len(json_responses) == len(sizes)
    return new_project_data, json_responses


def create_project_upload_data(
        requests, data, result_type='groups', binary=False, hash_size=None):
    if binary and hash_size is None:
        raise ValueError('binary mode must specify a hash_size')

    number_parties = len(data)
    new_project_data = create_project_no_data(
        requests, result_type=result_type, number_parties=number_parties)

    upload_url = url + f'/projects/{new_project_data["project_id"]}/clks'
    json_responses = []
    for clks, update_token in zip(data, new_project_data['update_tokens']):
        if binary:
            hash_count, mod = divmod(len(clks), hash_size)
            assert mod == 0
            r = requests.post(
                upload_url,
                headers={'Authorization': update_token,
                         'Content-Type': 'application/octet-stream',
                         'Hash-Count': str(hash_count),
                         'Hash-Size': str(hash_size)},
                data=clks)
        else:
            r = requests.post(
                upload_url,
                headers={'Authorization': update_token},
                json={'clks': clks})
        assert r.status_code == 201, f'Got this instead: {r.text}'
        json_responses.append(r.json())

    assert len(json_responses) == number_parties

    return new_project_data, json_responses


def _check_delete_response(r):
    # Note we allow for a 403 because the project may already have been deleted
    assert r.status_code in {204, 403}, 'I received this instead: {}'.format(r.text)
    # Delete project & run are both asynchronous so we generously allow the server some time to
    # delete resources before moving on (e.g. running the next test)
    time.sleep(0.5)


def delete_project(requests, project):
    project_id = project['project_id']
    result_token = project['result_token']
    r = requests.delete(url + '/projects/{}'.format(project_id),
                        headers={'Authorization': result_token})

    _check_delete_response(r)


def delete_run(requests, project_id, run_id, result_token):
    r = requests.delete(url + '/projects/{}/runs/{}'.format(project_id, run_id),
                        headers={'Authorization': result_token})
    _check_delete_response(r)


def get_run_status(requests, project, run_id, result_token = None):
    project_id = project['project_id']
    result_token = project['result_token'] if result_token is None else result_token
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(project_id, run_id),
                     headers={'Authorization': result_token})

    assert r.status_code == 200, 'I received this instead: {}'.format(r.text)
    return r.json()


def wait_for_run(requests, project, run_id, ok_statuses, result_token=None, timeout=10):
    """
    Poll project/run_id until its status is one of the ok_statuses. Raise a
    TimeoutError if we've waited more than timeout seconds.
    It also checks that the status are progressing normally, using the checks implemented in
    `has_not_progressed_invalidly`.
    """
    start_time = time.time()
    old_status = None
    while True:
        status = get_run_status(requests, project, run_id, result_token)
        if old_status:
            if not has_progressed_validly(old_status, status):
                raise Exception("The run has not progressed as expected. The old status "
                                "update was '{}' while the new one is '{}'.".format(old_status, status))
        if status['state'] in ok_statuses or status['state'] == 'error':
            break
        if time.time() - start_time > timeout:
            raise TimeoutError('waited for {}s'.format(timeout))
        time.sleep(0.5)
        old_status = status
    return status


def wait_for_run_completion(requests, project, run_id, result_token, timeout=20):
    completion_statuses = {'completed'}
    return wait_for_run(requests, project, run_id, completion_statuses, result_token, timeout)


def wait_while_queued(requests, project, run_id, result_token=None, timeout=10):
    not_queued_statuses = {'running', 'completed'}
    return wait_for_run(requests, project, run_id, not_queued_statuses, result_token, timeout)


def post_run(requests, project, threshold):
    project_id = project['project_id']
    result_token = project['result_token']

    req = requests.post(
        url + '/projects/{}/runs'.format(project_id),
        headers={'Authorization': result_token},
        json={'threshold': threshold})
    assert req.status_code == 201
    run_id = req.json()['run_id']
    # Each time we post a new run, we also check that the run endpoint works well.
    get_run(requests, project, run_id, expected_threshold=threshold)
    return run_id


def get_runs(requests, project, result_token=None, expected_status=200):
    project_id = project['project_id']
    result_token = project['result_token'] if result_token is None else result_token

    req = requests.get(
        url + '/projects/{}/runs'.format(project_id),
        headers={'Authorization': result_token})
    assert req.status_code == expected_status
    return req.json()


def get_run(requests, project, run_id, expected_status=200, expected_threshold=None):
    project_id = project['project_id']
    result_token = project['result_token']

    req = requests.get(
        url + '/projects/{}/runs/{}'.format(project_id, run_id),
        headers={'Authorization': result_token})

    assert req.status_code == expected_status
    run = req.json()
    if expected_status == 200:
        # only check these assertions if all went well.
        assert 'run_id' in run
        assert run['run_id'] == run_id
        assert 'notes' in run
        assert 'threshold' in run
        if expected_threshold:
            assert expected_threshold == run['threshold']
    return run


def get_run_result(requests, project, run_id, result_token=None, expected_status=200, wait=True, timeout=60):
    result_token = project['result_token'] if result_token is None else result_token
    if wait:
        # wait_for_run_completion also checks that the progress is in order.
        final_status = wait_for_run_completion(requests, project, run_id, result_token, timeout)
        state = final_status['state']
        assert state == 'completed', "Expected: 'completed', got: '{}'".format(state)

    project_id = project['project_id']
    r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
                     headers={'Authorization': result_token})
    assert r.status_code == expected_status
    return r.json()


def _check_new_project_response_fields(new_project_data):
    assert 'project_id' in new_project_data
    assert 'update_tokens' in new_project_data
    assert 'result_token' in new_project_data
    assert len(new_project_data['update_tokens']) == 2


class State(IntEnum):
    created = -1
    queued = 0
    running = 1
    completed = 2

    @staticmethod
    def from_string(state):
        if state == 'created':
            return State.created
        elif state == 'queued':
            return State.queued
        elif state == 'running':
            return State.running
        elif state == 'completed':
            return State.completed


def has_progressed_validly(status_old, status_new):
    """
    If there happened to be progress between the two statuses we check if it was valid.
    Thus, we return False if there was invalid progress, and True otherwise. (even if there was no progress)
    stage change counts as progress, but has to be done in the right order.
    also if both runs are in the same stage, we compare progress.

    :param status_old: json describing a run status as returned from the '/projects/{project_id}/runs/{run_id}/status'
                       endpoint
    :param status_new: same as above
    :return: False if the progress was not valid
    """
    old_stage = status_old['current_stage']['number']
    new_stage = status_new['current_stage']['number']

    if old_stage < new_stage:
        return True
    elif old_stage > new_stage:
        return False
    # both in the same stage then
    if 'progress' in status_old['current_stage'] and 'progress' in status_new['current_stage']:
        assert 0 <= status_new['current_stage']['progress']['relative'] <= 1.0, "{} not between 0 and 1".format(status_new['current_stage']['progress']['relative'])
        assert 0 <= status_old['current_stage']['progress']['relative'] <= 1.0, "{} not between 0 and 1".format(status_old['current_stage']['progress']['relative'])

        if status_new['current_stage']['progress']['relative'] < status_old['current_stage']['progress']['relative']:
            return False
        else:
            return True
    else:  # same stage, no progress info
        return True


def is_run_status(status):
    assert 'state' in status
    run_state = State.from_string(status['state'])
    assert run_state in State
    assert 'stages' in status
    assert 'time_added' in status
    assert 'current_stage' in status
    cur_stage = status['current_stage']

    if run_state == State.completed:
        assert 'time_started' in status
        assert 'time_completed' in status
    elif run_state == State.running:
        assert 'time_started' in status

    assert 'number' in cur_stage
    if 'progress' in cur_stage:
        assert 'absolute' in cur_stage['progress']
        assert 'relative' in cur_stage['progress']


def upload_binary_data(requests, data, project_id, token, count, size=128, expected_status_code=201):
    r = requests.post(
        url + '/projects/{}/clks'.format(project_id),
        headers={
            'Authorization': token,
            'Content-Type': 'application/octet-stream',
            'Hash-Count': str(count),
            'Hash-Size': str(size)
        },
        data=data
    )
    assert r.status_code == expected_status_code, 'I received this instead: {}'.format(r.text)

    upload_response = r.json()
    if expected_status_code == 201:
        assert 'receipt_token' in upload_response
    return upload_response


def upload_binary_data_from_file(requests, file_path, project_id, token, count, size=128, expected_status_code=201):
    with open(file_path, 'rb') as f:
        return upload_binary_data(requests, f, project_id, token, count, size, expected_status_code)


def get_expected_number_parties(project_params):
    return project_params.get('number_parties', 2)
