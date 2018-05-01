from entityservice.tests.config import url
from entityservice.tests.util import create_project_no_data, create_project_upload_fake_data


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