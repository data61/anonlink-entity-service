from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data


def test_empty_list_run(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': new_project_response['result_token']})

    assert r.status_code == 200
    assert r.json() == []


def test_list_run_noauth(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']))
    assert r.status_code == 400


def test_list_run_invalid_auth(requests):
    new_project_response, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])
    r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                     headers={'Authorization': 'invalid'})
    assert r.status_code == 403


def test_list_run_after_posting_runs(requests):
    new_project_response = create_project_no_data(requests)

    for i in range(1, 11):
        post_run_request = requests.post(
            url + '/projects/{}/runs'.format(new_project_response['project_id']),
            headers={'Authorization': new_project_response['result_token']},
            json={'threshold': 0.95}
        )
        assert post_run_request.status_code == 201

        # Check run listing has changed
        r = requests.get(url + '/projects/{}/runs'.format(new_project_response['project_id']),
                         headers={'Authorization': new_project_response['result_token']})

        assert r.status_code == 200
        assert len(r.json()) == i
