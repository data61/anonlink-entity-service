import base64
import datetime
import math
import random
import time
import warnings
from enum import IntEnum

import iso8601
from anonlink.util import generate_clks

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
    assert new_project_response.status_code == 201, 'I received this instead: {}'.format(new_project_response.text)
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
    assert r1.status_code == 201, 'I received this instead: {}'.format(r1.text)
    assert r2.status_code == 201, 'I received this instead: {}'.format(r2.text)

    return new_project_data, r1.json(), r2.json()


def delete_project(requests, project):
    project_id = project['project_id']
    result_token = project['result_token']
    r = requests.delete(url + '/projects/{}'.format(project_id),
                        headers={'Authorization': result_token})

    # Note we allow for a 403 because the project may already have been deleted
    assert r.status_code in {204, 403}, 'I received this instead: {}'.format(r.text)


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


def wait_for_run_completion(requests, project, run_id, result_token, timeout=20):
    completion_statuses = {'completed'}
    return wait_for_run(requests, project, run_id, completion_statuses, result_token, timeout)


def wait_while_queued(requests, project, run_id, result_token=None, timeout=10):
    not_queued_statuses = {'running', 'completed'}
    return wait_for_run(requests, project, run_id, not_queued_statuses, result_token, timeout)


def wait_approx_run_time(size, assumed_rate=1_000_000):
    """Calculate how long the similarity comparison stage of a project should take
    using a particular comparison rate. 1 M/s is quite conservative in order to work
    on slower CI systems.
    """
    size_1, size_2 = size
    time.sleep(3 + size_1 * size_2 / assumed_rate)


def ensure_run_progressing(requests, project, size):

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)

    if status['state'] not in {'completed', 'error'}:

        original_status = status

        dt = iso8601.parse_date(status['time_added'])
        assert datetime.datetime.now(tz=datetime.timezone.utc) - dt < datetime.timedelta(seconds=5)

        # Wait and see if the progress changes
        wait_approx_run_time(size)
        status = get_run_status(requests, project, run_id)
        if not has_progressed(original_status, status):
            wait_approx_run_time(size)
            status = get_run_status(requests, project, run_id)

        failure_msg = "No progress seen for run {}. Status A:\n{}\nStatus B:\n{}\n".format(run_id, original_status,
                                                                                           status)
        assert has_progressed(original_status, status), failure_msg


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


def get_run_result(requests, project, run_id, result_token = None, expected_status = 200, wait=True, timeout=30):
    result_token = project['result_token'] if result_token is None else result_token
    if wait:
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


def has_progressed(status_old, status_new):
    """
    stage change counts as progress, also if both runs are in the same stage, we compare progress. If no progress is
    available, we return True.

    :param status_old: json describing a run status as returned from the '/projects/{project_id}/runs/{run_id}/status'
                       endpoint
    :param status_new: same as above
    :return: True if there has been any progress, False otherwise
    """
    old_stage = status_old['current_stage']['number']
    new_stage = status_new['current_stage']['number']

    if old_stage < new_stage:
        return True
    elif old_stage > new_stage:
        raise ValueError("progress seems to go backwards! What's going on???")
    # both in the same stage then
    if 'progress' in status_old['current_stage'] and 'progress' in status_new['current_stage']:
        assert 0 <= status_new['current_stage']['progress']['relative'] <= 1.0, "{} not between 0 and 1".format(status_new['current_stage']['progress']['relative'])
        assert 0 <= status_old['current_stage']['progress']['relative'] <= 1.0, "{} not between 0 and 1".format(status_old['current_stage']['progress']['relative'])

        if status_new['current_stage']['progress']['relative'] > status_old['current_stage']['progress']['relative']:
            return True
        elif status_new['state'] == 'queued' and status_old['state'] == 'queued':
            warnings.warn("No progress because run was queued the whole time! Celery, what's up?")
            return False
        else:
            return False
    else:
        # how do you measure progress in that case??
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


def upload_binary_data(requests, file_path, project_id, token, count, expected_status_code=201):
    with open(file_path, 'rb') as f:
        r = requests.post(
            url + '/projects/{}/clks'.format(project_id),
            headers={
                'Authorization': token,
                'Content-Type': 'application/octet-stream',
                'Hash-Count': str(count),
                'Hash-Size':  '128'
            },
            data=f
        )
    assert r.status_code == expected_status_code

    upload_response = r.json()
    if expected_status_code == 201:
        assert 'receipt_token' in upload_response
    return upload_response
