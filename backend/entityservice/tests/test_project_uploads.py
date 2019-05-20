import time
import os
import pytest

from entityservice.serialization import binary_pack_filters
from entityservice.tests.config import url
from entityservice.tests.util import generate_json_serialized_clks, upload_binary_data_from_file, post_run, \
    get_run_result, \
    generate_clks, upload_binary_data, create_project_upload_fake_data, get_run, create_project_upload_data


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
            'clks': generate_json_serialized_clks(100)
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

    small_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_128B_1k.bin')

    upload_binary_data_from_file(requests, small_file_path, new_project_data['project_id'], new_project_data['update_tokens'][0], 1000)
    upload_binary_data_from_file(requests, small_file_path, new_project_data['project_id'], new_project_data['update_tokens'][1], 1000)

    run_id = post_run(requests, new_project_data, 0.99)
    result = get_run_result(requests, new_project_data, run_id, wait=True)
    assert 'mapping' in result

    # Since we uploaded the same file it should have identified the same rows as matches
    for i in range(1, 1000):
        assert str(i) in result['mapping']
        assert result['mapping'][str(i)] == str(i)


def test_project_binary_data_upload_with_different_encoded_size(requests, encoding_size):

    new_project_data = requests.post(url + '/projects',
                                 json={
                                     'schema': {},
                                     'result_type': 'mapping',
                                 }).json()

    g1 = binary_pack_filters(generate_clks(499, encoding_size), encoding_size)
    g2 = binary_pack_filters(generate_clks(499, encoding_size), encoding_size)
    g3 = binary_pack_filters(generate_clks(1, encoding_size), encoding_size)
    def convert_generator_to_bytes(g):
        return b''.join(g)

    shared_entity = next(g3)
    f1 = convert_generator_to_bytes(g1) + shared_entity
    f2 = shared_entity + convert_generator_to_bytes(g2)

    assert len(f1) == 500 * encoding_size

    upload_binary_data(requests, f1, new_project_data['project_id'], new_project_data['update_tokens'][0], 500, size=encoding_size)
    upload_binary_data(requests, f2, new_project_data['project_id'], new_project_data['update_tokens'][1], 500, size=encoding_size)

    print('ENC SIZE', encoding_size)

    run_id = post_run(requests, new_project_data, 0.99)
    result = get_run_result(requests, new_project_data, run_id, wait=True)
    assert 'mapping' in result
    assert result['mapping']['499'] == '0'


def test_project_json_data_upload_with_various_encoded_sizes(requests, encoding_size):
    new_project_data, (r1, r2) = create_project_upload_fake_data(
        requests,
        [500, 500],
        overlap=0.95,
        result_type='mapping',
        encoding_size=encoding_size
    )

    run_id = post_run(requests, new_project_data, 0.9)
    result = get_run_result(requests, new_project_data, run_id, wait=True)
    assert 'mapping' in result
    assert len(result['mapping']) >= 475


def test_project_json_data_upload_with_mismatched_encoded_size(requests):
    d1 = generate_json_serialized_clks(500, 64)
    d2 = generate_json_serialized_clks(500, 256)

    new_project_data, (r1, r2) = create_project_upload_data(
        requests, (d1, d2), result_type='mapping')

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_invalid_encoded_size(requests):

    new_project_data, (r1, r2) = create_project_upload_fake_data(
        requests,
        [500, 500],
        overlap=0.95,
        result_type='mapping',
        encoding_size=20    # not multiple of 8
    )

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_too_small_encoded_size(requests):
    new_project_data, (r1, r2) = create_project_upload_fake_data(
        requests,
        [500, 500],
        overlap=0.95,
        result_type='mapping',
        encoding_size=4
    )

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_too_large_encoded_size(requests):
    new_project_data, (r1, r2) = create_project_upload_fake_data(
        requests,
        [50, 50],
        overlap=0.95,
        result_type='mapping',
        encoding_size=4096
    )

    time.sleep(5)
    project_description = requests.get(
        url + '/projects/{}'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['result_token']}
    ).json()
    assert 'error' in project_description
    assert project_description['error']


def test_project_binary_data_invalid_buffer_size(requests):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     }).json()
    pid = new_project_data['project_id']
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_128B_1k.bin')

    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], -1, status=400)

    # Now try upload with valid hash-count but doesn't match actual size:
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 1000000, status=400)
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 3, status=400)

    # Now try the minimum upload size (1 clk)
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/single_clk.bin')
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 1, status=201)


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

