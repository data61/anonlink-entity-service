import datetime
import time

import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data


def test_run_status_with_clks(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={
            'threshold': 0.90
        }
    )

    time_posted = datetime.datetime.now(tz=datetime.timezone.utc)

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

    assert time_posted - dt < datetime.timedelta(seconds=5)
    original_progress = status['progress']['progress']

    # Wait and see if the progress changes. Project should easily be complete
    time.sleep(5)
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
            new_project_response['project_id'],
            post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})
    status = r.json()

    if original_progress != 1.0:
        assert status['progress']['progress'] > original_progress

    assert status['state'] == 'completed'
    assert 'time_started' in status
    assert 'time_completed' in status


def test_run_status_without_clks(requests):
    new_project_response = create_project_no_data(requests)

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={'threshold': 0.90}
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
    assert status['state'] == 'queued'
