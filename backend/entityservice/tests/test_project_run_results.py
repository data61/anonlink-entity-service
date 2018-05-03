import pytest

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data, wait_for_run_completion


def test_run_mapping_results(requests, example_mapping_projects):
    for example_mapping_project in example_mapping_projects:
        post_run_request = requests.post(
            url + '/projects/{}/runs'.format(example_mapping_project['project_id']),
            headers={'Authorization': example_mapping_project['result_token']},
            json={'threshold': 0.95}
        )
        assert post_run_request.status_code == 201
        project_id = example_mapping_project['project_id']
        result_token = example_mapping_project['result_token']
        run_id = post_run_request.json()['run_id']

        final_status = wait_for_run_completion(requests, project_id, run_id, result_token)
        assert final_status['state'] == 'completed'
        # Get results
        r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
            headers={'Authorization': result_token})
        result = r.json()

        assert 'mapping' in result
        assert isinstance(result['mapping'], dict)


@pytest.mark.parametrize("threshold", [0.6, 0.9, 1.0])
def test_run_similarity_score_results(requests, example_similarity_projects, threshold):
    for project in example_similarity_projects:
        post_run_request = requests.post(
            url + '/projects/{}/runs'.format(project['project_id']),
            headers={'Authorization': project['result_token']},
            json={'threshold': threshold}
        )
        assert post_run_request.status_code == 201
        project_id = project['project_id']
        result_token = project['result_token']
        run_id = post_run_request.json()['run_id']

        final_status = wait_for_run_completion(requests, project_id, run_id, result_token)
        assert final_status['state'] == 'completed'
        # Get results
        r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
            headers={'Authorization': result_token})
        result = r.json()

        assert 'similarity_scores' in result


@pytest.mark.parametrize("threshold", [0.9, 0.999])
def test_run_permutation_unencrypted_results(requests, example_permutation_projects, threshold):
    for project in example_permutation_projects:
        post_run_request = requests.post(
            url + '/projects/{}/runs'.format(project['project_id']),
            headers={'Authorization': project['result_token']},
            json={'threshold': threshold}
        )
        assert post_run_request.status_code == 201
        project_id = project['project_id']
        result_token = project['result_token']
        run_id = post_run_request.json()['run_id']

        final_status = wait_for_run_completion(requests, project_id, run_id, result_token)
        assert final_status['state'] == 'completed'
        # Get results using result_token
        r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
            headers={'Authorization': result_token})
        mask_result = r.json()

        assert 'mask' in mask_result
        assert len(mask_result['mask']) == min(project['size'])

        # Get results using receipt_token A and B
        r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
            headers={'Authorization': project['dp_1']['receipt_token']})
        assert r.status_code == 200
        result = r.json()
        assert 'permutation' in result
        assert 'rows' in result
        assert result['rows'] == len(mask_result['mask'])

        r = requests.get(url + '/projects/{}/runs/{}/result'.format(project_id, run_id),
            headers={'Authorization': project['dp_2']['receipt_token']})
        assert r.status_code == 200
        result2 = r.json()
        assert 'permutation' in result2
        assert 'rows' in result2
        assert result2['rows'] == result['rows']
        assert result2['rows'] == len(mask_result['mask'])


def test_run_mapping_results_no_data(requests):
    new_project_response = create_project_no_data(requests)

    post_run_request = requests.post(
        url + '/projects/{}/runs'.format(new_project_response['project_id']),
        headers={'Authorization': new_project_response['result_token']},
        json={'threshold': 0.95}
    )
    assert post_run_request.status_code == 201

    r = requests.get(url + '/projects/{}/runs/{}/result'.format(
            new_project_response['project_id'],
            post_run_request.json()['run_id']
        ),
        headers={'Authorization': new_project_response['result_token']})
    assert r.status_code == 404
