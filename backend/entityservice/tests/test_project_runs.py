import datetime
import time

import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, has_progressed


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
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    original_status = status

    dt = iso8601.parse_date(status['time_added'])
    assert datetime.datetime.now(tz=datetime.timezone.utc) - dt < datetime.timedelta(seconds=5)

    # Wait and see if the progress changes
    time.sleep(30)
    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        new_project_response['project_id'],
        post_run_request.json()['run_id']
    ),
                     headers={'Authorization': new_project_response['result_token']})
    status = r.json()
    assert has_progressed(original_status, status)

