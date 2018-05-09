import datetime
import time
from requests import sessions
import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data, has_progressed


def wait_while_queued(request, timeout=30, interval=1):
    """
    waits for maximum 'timeout' seconds for this run to change its state to something other than 'queued'.
    """
    start = datetime.datetime.now()
    while datetime.datetime.now() - start < datetime.timedelta(seconds=timeout):
        with sessions.Session() as session:
            response = session.send(request)
        if response.json().get('state') is not 'queued':
            return response
        time.sleep(interval)
    raise TimeoutError('timeout reached while waiting for this run to un-queue...')


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

    r = wait_while_queued(r.request)

    assert r.status_code == 200
    status = r.json()

    assert 'state' in status
    assert 'message' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    if status['state'] == 'running':
        assert 'time_started' in status
        assert 'progress' in status
    elif status['state'] == 'completed':
        assert 'time_started' in status
        assert 'time_completed' in status

    dt = iso8601.parse_date(status['time_added'])

    assert time_posted - dt < datetime.timedelta(seconds=5)
    original_status = status

    # Wait and see if the progress changes. Project should easily be complete
    time.sleep(5)
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
            new_project_response['project_id'],
            post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})
    status = r.json()

    assert has_progressed(original_status, status)


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
    assert 'time_added' in status
    assert status['state'] == 'queued'
