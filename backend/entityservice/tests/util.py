import random
import time
from enum import IntEnum


from anonlink.util import generate_clks

import math

import base64

from entityservice.tests.config import url


def serialize_bitarray(ba):
    """ Serialize a bitarray (bloomfilter)

    """
    return base64.encodebytes(ba.tobytes()).decode('utf8')


def serialize_filters(filters):
    """Serialize filters as clients are required to."""
    return [
        serialize_bitarray(f[0]) for f in filters
    ]


def generate_serialized_clks(size):
    clks = generate_clks(size)
    return [serialize_bitarray(clk) for clk,_ ,_ in clks]


def generate_overlapping_clk_data(dataset_sizes, overlap=0.9):

    datasets = []
    for size in dataset_sizes:
        datasets.append(generate_serialized_clks(size))

    overlap_to = math.floor(min(dataset_sizes)*overlap)
    for ds in datasets[1:]:
        ds[:overlap_to] = datasets[0][:overlap_to]
        random.shuffle(ds)

    return datasets


def get_project_description(requests, new_project_data):
    project_description_response = requests.get(url + '/projects/{}'.format(new_project_data['project_id']),
                            headers={'Authorization': new_project_data['result_token']})

    assert project_description_response.status_code == 200
    return project_description_response.json()


def create_project_no_data(requests, result_type='mapping'):
    new_project_response = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         'result_type': result_type,
                                     })
    assert new_project_response.status_code == 201, 'I received this instead: {}'.format(new_project_response.json())
    return new_project_response.json()


def create_project_upload_fake_data(requests, size, overlap=0.75, result_type='mapping'):
    d1, d2 = generate_overlapping_clk_data(size, overlap=overlap)
    return create_project_upload_data(requests, d1, d2, result_type=result_type)


def create_project_upload_data(requests, clks1, clks2, result_type='mapping'):
    new_project_data = create_project_no_data(requests, result_type=result_type)

    r1 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': clks1
        }
    )
    r2 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][1]},
        json={
            'clks': clks2
        }
    )
    assert r1.status_code == 201, 'I received this instead: {}'.format(r1.json())
    assert r2.status_code == 201, 'I received this instead: {}'.format(r2.json())

    return new_project_data, r1.json(), r2.json()


def get_run_status(requests, project, run_id, result_token = None):
    project_id = project['project_id']
    result_token = project['result_token'] if result_token is None else result_token
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(project_id, run_id),
                     headers={'Authorization': result_token})

    assert r.status_code == 200, 'I received this instead: {}'.format(r.json())
    return r.json()


def wait_for_run(requests, project, run_id, ok_statuses, result_token=None, timeout=10):
    """
    Poll project/run_id until its status is one of the ok_statuses. Raise a
    TimeoutError if we've waited more than timeout seconds.
    """
    start_time = time.time()
    while True:
        status = get_run_status(requests, project, run_id, result_token)
        if status['state'] in ok_statuses:
            break
        if time.time() - start_time > timeout:
            raise TimeoutError('waited for {}s'.format(timeout))
        time.sleep(0.1)

    return status


def wait_for_run_completion(requests, project, run_id, result_token, timeout=10):
    completion_statuses = {'completed'}
    return wait_for_run(requests, project, run_id, result_token, completion_statuses, timeout)


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
    return req.json()['run_id']


def get_runs(requests, project, result_token = None, expected_status = 200):
    project_id = project['project_id']
    result_token = project['result_token'] if result_token is None else result_token

    req = requests.get(
        url + '/projects/{}/runs'.format(project_id),
        headers={'Authorization': result_token})
    assert req.status_code == expected_status
    return req.json()


def get_run(requests, project, run_id, expected_status = 200):
    project_id = project['project_id']
    result_token = project['result_token']

    req = requests.get(
        url + '/projects/{}/runs/{}'.format(project_id, run_id),
        headers={'Authorization': result_token})
    assert req.status_code == expected_status
    return req.json()


def get_run_result(requests, project, run_id, result_token = None, expected_status = 200, wait=True):
    result_token = project['result_token'] if result_token is None else result_token
    if wait:
        final_status = wait_for_run_completion(requests, project, run_id, result_token)
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
    queued = 0
    running = 1
    completed = 2

    @staticmethod
    def from_string(state):
        if state == 'queued':
            return State.queued
        elif state == 'running':
            return State.running
        elif state == 'completed':
            return State.completed


def has_progressed(status_old, status_new):
    """
    state change counts as progress, also if both are running, we compare progress. If both are finished we return
    True.

    :param status_old: json describing a run status as returned from the '/projects/{project_id}/runs/{run_id}/status'
                       endpoint
    :param status_new: same as above
    :return: True if there has been any progress, False otherwise
    """
    old_state = State.from_string(status_old['state'])
    new_state = State.from_string(status_new['state'])

    if old_state < new_state:
        return True
    elif old_state > new_state:
        raise ValueError("progress seems to go backwards! What's going on???")
    # now both states are the same
    if new_state == State.queued:
        return False
    if new_state == State.completed:
        return True
    return status_new['progress']['progress'] > status_old['progress']['progress']
