import datetime
import time

import iso8601
import pytest

from entityservice.tests.config import url
from entityservice.tests.util import generate_serialized_clks, generate_overlapping_clk_data, get_project_description, \
    create_project_upload_fake_data, create_project_no_data


def _check_new_project_response_fields(new_project_data):
    assert 'project_id' in new_project_data
    assert 'update_tokens' in new_project_data
    assert 'result_token' in new_project_data
    assert len(new_project_data['update_tokens']) == 2


def test_empty_list_run(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    assert r.json() == []


def test_list_run_noauth(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']))
    assert r.status_code == 401


def test_list_run_invalid_auth(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': 'invalid'})
    assert r.status_code == 403


def test_posting_run_before_data_upload(requests):
    new_project_response = create_project_no_data(requests)

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.95
        }
    )

    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    run = runs[0]
    assert 'run_id' in run
    assert 'time_added' in run
    assert 'state' in run
    assert run['state'] == 'queued'


def test_posting_run_after_data_upload(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.95
        }
    )

    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    for run in runs:
        assert 'run_id' in run
        assert 'time_added' in run
        assert 'state' in run


def test_run_description_missing_run(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    r = requests.get(url + '/projects/{}/runs/{}'.format(
        new_project_response['project_id'],
        'invalid'
        ),
        headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 403


def test_run_description(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.95
        }
    )

    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs/{}'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    run = r.json()

    assert 'run_id' in run
    assert 'notes' in run
    assert 'threshold' in run


def test_run_status(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.90
        }
    )

    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    status = r.json()

    assert 'state' in status
    assert 'message' in status
    assert 'progress' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    if status['state'] == 'running':
        assert 'time_started' in status
    elif status['state'] == 'completed':
        assert 'time_started' in status
        assert 'time_completed' in status

    dt = iso8601.parse_date(status['time_added'])
    assert datetime.datetime.now(tz=datetime.timezone.utc) - dt < datetime.timedelta(seconds=5)
    original_progress = status['progress']['progress']

    # Wait and see if the progress changes
    time.sleep(2)
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
    ),
                     headers={'Authorization': new_project_response['result_token']})
    status = r.json()
    assert status['progress']['progress'] > original_progress


def test_run_larger(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [100000, 10000])

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.90
        }
    )

    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    status = r.json()

    assert 'state' in status
    assert 'message' in status
    assert 'progress' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    if status['state'] == 'running':
        assert 'time_started' in status
    elif status['state'] == 'completed':
        assert 'time_started' in status
        assert 'time_completed' in status

    dt = iso8601.parse_date(status['time_added'])
    assert datetime.datetime.now(tz=datetime.timezone.utc) - dt < datetime.timedelta(seconds=5)
    original_progress = status['progress']['progress']

    # Wait and see if the progress changes
    time.sleep(30)
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
    ),
                     headers={'Authorization': new_project_response['result_token']})
    status = r.json()
    assert status['progress']['progress'] > original_progress