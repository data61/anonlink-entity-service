from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data


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
