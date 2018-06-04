import os

from entityservice.tests.config import url
from entityservice.tests.util import generate_serialized_clks, upload_binary_data


def test_project_single_party_data_uploaded(requests):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     }).json()
    r = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': generate_serialized_clks(100)
        }
    )
    assert r.status_code == 201
    upload_response = r.json()
    assert 'receipt_token' in upload_response


def test_project_binary_data_uploaded(requests):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     }).json()

    small_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/single_clk.bin')
    large_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_1k.bin')
    upload_binary_data(requests, small_file_path, new_project_data['project_id'], new_project_data['update_tokens'][0], 1)
    upload_binary_data(requests, large_file_path, new_project_data['project_id'], new_project_data['update_tokens'][1], 1000)

    # TODO Need to test that we can post a run and get results too


def test_project_binary_data_invalid_buffer_size(requests):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     }).json()
    pid = new_project_data['project_id']
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_1k.bin')

    upload_binary_data(requests, file_path, pid, new_project_data['update_tokens'][0], -1, 400)

    # Now try upload with valid hash-count but doesn't match actual size:
    upload_binary_data(requests, file_path, pid, new_project_data['update_tokens'][0], 1000000, 400)
    upload_binary_data(requests, file_path, pid, new_project_data['update_tokens'][0], 3, 400)


def test_mapping_single_party_empty_data_upload(requests):
    new_project_data = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     }).json()


    r = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': []
        }
    )
    assert r.status_code == 400

