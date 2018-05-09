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
    assert new_project_response.status_code == 201
    return new_project_response.json()


def create_project_upload_fake_data(requests, size, overlap=0.75, result_type='mapping'):
    new_project_data = create_project_no_data(requests, result_type=result_type)

    d1, d2 = generate_overlapping_clk_data(size, overlap=overlap)
    r1 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': d1
        }
    )
    r2 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][1]},
        json={
            'clks': d2
        }
    )
    assert r1.status_code == 201
    assert r2.status_code == 201

    return new_project_data, r1.json(), r2.json()


def wait_for_run_completion(requests, project_id, run_id, result_token, timeout=30):
    start_time = time.time()
    status = get_run_status(requests, project_id, run_id, result_token)
    while status['state'] in {'queued', 'running'} and time.time() - start_time < timeout:
        status = get_run_status(requests, project_id, run_id, result_token)
        time.sleep(0.1)

    return status


def get_run_status(requests, project_id, run_id, result_token):
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
            project_id,
            run_id
        ),
        headers={'Authorization': result_token})

    assert r.status_code == 200
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
