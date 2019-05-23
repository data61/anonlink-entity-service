import itertools
import time

import pytest

from entityservice.tests.config import url
from entityservice.tests.util import generate_overlapping_clk_data, get_project_description, delete_project


@pytest.fixture
def valid_project_param(request, result_type_number_parties_or_none):
    result_type, number_parties_or_none = result_type_number_parties_or_none
    # None is what we use to test handling of default values
    params_dict = {'result_type': result_type}
    if number_parties_or_none is not None:
        params_dict['number_parties'] = number_parties_or_none
    expected_parties_value = number_parties_or_none or 2
    return params_dict, expected_parties_value


def _check_new_project_response_fields(new_project_data,
                                       expected_number_parties):
    assert 'project_id' in new_project_data
    assert 'update_tokens' in new_project_data
    assert 'result_token' in new_project_data
    assert len(new_project_data['update_tokens']) == expected_number_parties


def test_simple_create_project(requests, valid_project_param):
    project_name = 'a test project'
    project_description = 'created by unittest'

    params_dict, expected_number_parties = valid_project_param
    project_response = requests.post(url + '/projects', json={
        'schema': {},
        'name': project_name,
        'notes': project_description,
        **params_dict
    })

    assert project_response.status_code == 201
    new_project_data = project_response.json()
    _check_new_project_response_fields(
        new_project_data, expected_number_parties)


def test_create_then_delete_no_auth(requests, valid_project_param):
    params_dict, expected_number_parties = valid_project_param
    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    })
    assert new_project_response.status_code == 201
    _check_new_project_response_fields(
        new_project_response.json(), expected_number_parties)

    delete_project_response = requests.delete(url + '/projects/{}'.format(new_project_response.json()['project_id']))
    assert 400 == delete_project_response.status_code


def test_create_then_delete_invalid_auth(requests, valid_project_param):
    params_dict, expected_number_parties = valid_project_param
    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    })
    assert new_project_response.status_code == 201
    _check_new_project_response_fields(
        new_project_response.json(), expected_number_parties)

    delete_project_response = requests.delete(
        url + '/projects/{}'.format(new_project_response.json()['project_id']),
        headers={'Authorization': 'invalid'}
    )
    assert delete_project_response.status_code == 403


def test_create_then_delete_valid_auth(requests, valid_project_param):
    params_dict, expected_number_parties = valid_project_param
    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    })
    assert new_project_response.status_code == 201
    _check_new_project_response_fields(
        new_project_response.json(), expected_number_parties)

    token = new_project_response.json()['result_token']
    delete_project_response = requests.delete(
        url + '/projects/{}'.format(new_project_response.json()['project_id']),
        headers={'Authorization': token}
    )
    assert delete_project_response.status_code == 204


def test_delete_project_types(requests, project):
    delete_project(requests, project)


def test_create_then_list(requests, valid_project_param):
    original_project_list_respose = requests.get(url + '/projects').json()
    original_project_ids = [p['project_id'] for p in original_project_list_respose]

    params_dict, _ = valid_project_param
    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    }).json()

    assert new_project_response['project_id'] not in original_project_ids

    project_list_response = requests.get(url + '/projects').json()
    new_project_ids = [p['project_id'] for p in project_list_response]

    assert new_project_response['project_id'] in new_project_ids


def test_create_then_describe_noauth(requests, valid_project_param):
    params_dict, _ = valid_project_param
    new_project = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    }).json()

    r = requests.get(url + '/projects/{}'.format(new_project['project_id']))
    assert 400 == r.status_code


def test_create_then_describe_invalid_auth(requests, valid_project_param):
    params_dict, _ = valid_project_param
    project_respose = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    }).json()
    r = requests.get(
        url + '/projects/{}'.format(project_respose['project_id']),
        headers={'Authorization': 'invalid'}
    )
    assert r.status_code == 403


def test_create_then_describe_valid_auth(requests, valid_project_param):
    params_dict, expected_number_parties = valid_project_param
    project_respose = requests.post(url + '/projects', json={
        'schema': {},
        **params_dict
    }).json()
    r = requests.get(
        url + '/projects/{}'.format(project_respose['project_id']),
        headers={'Authorization': project_respose['result_token']}
    )
    assert r.status_code == 200
    project_description = r.json()

    assert 'project_id' in project_description
    assert 'name' in project_description
    assert 'notes' in project_description
    assert 'schema' in project_description
    assert 'error' in project_description
    assert not project_description['error']
    assert 'public_key' not in project_description
    assert 'paillier_context' not in project_description

    assert params_dict['result_type'] == project_description['result_type']
    assert expected_number_parties == project_description['number_parties']
    assert '' == project_description['name'], 'default name should be blank'
    assert '' == project_description['notes'], 'default notes should be blank'


def test_describe_missing_project_with_invalidauth(requests):
    r = requests.get(
        url + '/projects/{}'.format('fakeprojectid'),
        headers={'Authorization': 'invalid'}
    )
    assert r.status_code == 403


def test_list_runs_of_missing_project_with_invalidauth(requests):
    r = requests.get(
        url + '/projects/{}/runs'.format('fakeprojectid'),
        headers={'Authorization': 'invalid'}
    )
    assert r.status_code == 403


def test_data_uploaded(requests, valid_project_param):
    params_dict, expected_number_parties = valid_project_param
    new_project_data = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         **params_dict
                                     }).json()
    description_1 = get_project_description(requests, new_project_data)
    assert description_1['number_parties'] == expected_number_parties
    assert description_1['parties_contributed'] == 0

    datasets = generate_overlapping_clk_data(
        [100] * expected_number_parties, overlap=0.8)
    for i, dataset, update_token in zip(itertools.count(1),
                                        datasets,
                                        new_project_data['update_tokens']):
        r = requests.post(
            url + '/projects/{}/clks'.format(new_project_data['project_id']),
            headers={'Authorization': update_token},
            json={
                'clks': dataset
            }
        )
        assert r.status_code == 201
        time.sleep(0.5)
        description_2 = get_project_description(requests, new_project_data)
        assert description_2['number_parties'] == expected_number_parties
        assert description_2['parties_contributed'] == i


def test_fail_on_invalid_result_type_number_parties(
        requests,
        invalid_result_type_number_parties):
    result_type, number_parties = invalid_result_type_number_parties
    r = requests.post(url + '/projects', json={
        'schema': {},
        'result_type': result_type,
        'number_parties': number_parties
    })
    assert r.status_code == 400


def test_invalid_result_type_number_parties_does_not_side_effect(
        requests,
        invalid_result_type_number_parties):
    result_type, number_parties = invalid_result_type_number_parties
    
    original_project_list_respose = requests.get(url + '/projects').json()
    original_project_ids = {
        p['project_id'] for p in original_project_list_respose}

    requests.post(url + '/projects', json={
        'schema': {},
        'result_type': result_type,
        'number_parties': number_parties
    })

    new_project_list_respose = requests.get(url + '/projects').json()
    new_project_ids = {
        p['project_id'] for p in new_project_list_respose}

    assert original_project_ids == new_project_ids
