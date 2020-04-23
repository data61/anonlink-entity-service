import time
import os
import pytest
from minio import Minio

from e2etests.config import url
from e2etests.util import (
    create_project_upload_data, create_project_upload_fake_data,
    generate_clks, generate_json_serialized_clks,
    get_expected_number_parties, get_run_result, post_run,
    upload_binary_data, upload_binary_data_from_file, binary_pack_for_upload)


def test_project_single_party_data_uploaded_clks_format(requests, valid_project_params):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    r = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': generate_json_serialized_clks(100)
        }
    )
    assert r.status_code == 201, r.text
    upload_response = r.json()
    assert 'receipt_token' in upload_response


def test_project_single_party_data_uploaded_clknblocks_format(requests, a_blocking_project):

    clksnblocks = [[encoding, '1'] for encoding in generate_json_serialized_clks(10)]

    r = requests.post(
        url + '/projects/{}/clks'.format(a_blocking_project['project_id']),
        headers={'Authorization': a_blocking_project['update_tokens'][0]},
        json={
            'clknblocks': clksnblocks
        }
    )
    assert r.status_code == 201, r.text
    upload_response = r.json()
    assert 'receipt_token' in upload_response


def test_project_single_party_data_uploaded_encodings_format(requests, valid_project_params):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    r = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'encodings': generate_json_serialized_clks(100)
        }
    )
    assert r.status_code == 201, r.text
    upload_response = r.json()
    assert 'receipt_token' in upload_response


def test_project_single_party_data_uploaded_encodings_and_blocks_format(requests, a_blocking_project):
    encodings = generate_json_serialized_clks(10)
    blocks = {encoding_id: ['1'] for encoding_id in range(len(encodings))}

    r = requests.post(
        url + '/projects/{}/clks'.format(a_blocking_project['project_id']),
        headers={'Authorization': a_blocking_project['update_tokens'][0]},
        json={
            'encodings': encodings,
            'blocks': blocks
        }
    )
    assert r.status_code == 201, r.text
    upload_response = r.json()
    assert 'receipt_token' in upload_response


def test_project_external_data_uploaded(requests, a_project, binary_test_file_path):

    r = requests.get(
        url + 'projects/{}/authorize-external-upload'.format(a_project['project_id']),
        headers={'Authorization': a_project['update_tokens'][0]},
    )
    assert r.status_code == 201
    upload_response = r.json()

    credentials = upload_response['credentials']
    upload_info = upload_response['upload']

    # Use Minio python client to upload data
    mc = Minio(
        'localhost:9000', #upload_info['endpoint'],
        access_key=credentials['AccessKeyId'],
        secret_key=credentials['SecretAccessKey'],
        session_token=credentials['SessionToken'],
        region='us-east-1',
        secure=upload_info['secure']
    )

    etag = mc.fput_object(
        upload_info['bucket'],
        upload_info['path'] + "/test",
        binary_test_file_path,
        metadata={
            "hash-count": 99,
            "hash-size": 128
        }
    )

    # Should be able to notify the service that we've uploaded data
    res = requests.post(url + f"projects/{a_project['project_id']}/clks",
                        headers={'Authorization': a_project['update_tokens'][0]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/test",
                                }
                            }
                        }
                       )
    assert res.status_code == 201


def test_project_binary_data_uploaded(requests, valid_project_params, binary_test_file_path):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    update_tokens = new_project_data['update_tokens']
    expected_number_parties = get_expected_number_parties(valid_project_params)
    assert len(update_tokens) == expected_number_parties

    for token in update_tokens:
        upload_binary_data_from_file(
            requests,
            binary_test_file_path, new_project_data['project_id'], token, 1000)

    run_id = post_run(requests, new_project_data, 0.99)
    result = get_run_result(requests, new_project_data, run_id, wait=True)

    if valid_project_params['result_type'] == 'groups':
        assert 'groups' in result
        groups = result['groups']
        assert len(groups) == 1000
        for group in groups:
            dataset_indices = {di for di, _ in group}
            record_indices = {ri for _, ri in group}
            assert len(record_indices) == 1
            assert dataset_indices == set(range(expected_number_parties))
        # Check every record is represented
        all_record_indices = {next(iter(group))[1] for group in groups}
        assert all_record_indices == set(range(1000))


def test_project_binary_data_upload_with_different_encoded_size(
        requests,
        encoding_size, valid_project_params):
    expected_number_parties = get_expected_number_parties(valid_project_params)
    new_project_data = requests.post(url + '/projects',
                                 json={
                                     'schema': {},
                                     **valid_project_params
                                 }).json()

    common = next(binary_pack_for_upload(generate_clks(1, encoding_size),
                                      encoding_size))

    data = []
    for i in range(expected_number_parties):
        generated_clks = generate_clks(499, encoding_size)
        packed_clks = binary_pack_for_upload(generated_clks, encoding_size)
        packed_joined = b''.join(packed_clks)
        packed_with_common = (
            packed_joined + common if i == 0 else common + packed_joined)
        data.append(packed_with_common)

    project_id = new_project_data['project_id']
    for d, token in zip(data, new_project_data['update_tokens']):
        assert len(d) == 500 * encoding_size
        upload_binary_data(
            requests, d, project_id, token, 500, size=encoding_size)

    run_id = post_run(requests, new_project_data, 0.99)
    result = get_run_result(requests, new_project_data, run_id, wait=True)
    if valid_project_params['result_type'] == 'groups':
        assert 'groups' in result
        groups = result['groups']
        groups_set = {frozenset(map(tuple, group)) for group in groups}
        common_set = frozenset(
            (i, 499 if i == 0 else 0) for i in range(expected_number_parties))
        assert common_set in groups_set


def test_project_json_data_upload_with_various_encoded_sizes(
        requests,
        encoding_size, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    new_project_data, _ = create_project_upload_fake_data(
        requests,
        [500] * number_parties,
        overlap=0.8,
        result_type=result_type,
        encoding_size=encoding_size
    )

    run_id = post_run(requests, new_project_data, 0.9)
    result = get_run_result(requests, new_project_data, run_id, wait=True)
    if result_type == 'groups':
        assert 'groups' in result
        # This is a pretty bad bound, but we're not testing the
        # accuracy.
        assert len(result['groups']) >= 400


def test_project_json_data_upload_with_mismatched_encoded_size(
        requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties

    data = [generate_json_serialized_clks(500, 64 if i == 0 else 256)
            for i in range(number_parties)]

    new_project_data, _ = create_project_upload_data(
        requests, data, result_type=result_type)

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_invalid_encoded_size(
        requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    new_project_data, _ = create_project_upload_fake_data(
        requests,
        [500] * number_parties,
        overlap=0.8,
        result_type=result_type,
        encoding_size=20    # not multiple of 8
    )

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_too_small_encoded_size(
        requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    new_project_data, _ = create_project_upload_fake_data(
        requests,
        [500] * number_parties,
        overlap=0.8,
        result_type=result_type,
        encoding_size=4
    )

    with pytest.raises(AssertionError):
        run_id = post_run(requests, new_project_data, 0.9)
        get_run_result(requests, new_project_data, run_id, wait=True)


def test_project_json_data_upload_with_too_large_encoded_size(
        requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    new_project_data, _ = create_project_upload_fake_data(
        requests,
        [500] * number_parties,
        overlap=0.8,
        result_type=result_type,
        encoding_size=4096
    )
    # Just initializing it before the loop.
    project_description = {'error': False}
    rep = 0
    max_rep = 10
    while not project_description['error'] and rep < max_rep:
        rep += 1
        time.sleep(2)
        project_description = requests.get(
            url + '/projects/{}'.format(new_project_data['project_id']),
            headers={'Authorization': new_project_data['result_token']}
        ).json()
        assert 'error' in project_description

    assert project_description['error']


def test_project_binary_data_invalid_buffer_size(
        requests, valid_project_params):
    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    pid = new_project_data['project_id']
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_128B_1k.bin')

    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], -1, expected_status_code=400)

    # Now try upload with valid hash-count but doesn't match actual size:
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 1000000, expected_status_code=400)
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 3, expected_status_code=400)

    # Now try the minimum upload size (1 clk)
    file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/single_clk.bin')
    upload_binary_data_from_file(requests, file_path, pid, new_project_data['update_tokens'][0], 1, expected_status_code=201)


def test_project_single_party_empty_data_upload(
        requests, valid_project_params):
    new_project_data = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()

    r = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': []
        }
    )
    assert r.status_code == 400


def test_project_upload_using_twice_same_authentication(requests, valid_project_params):
    """
    Test that a token cannot be re-used to upload clks.
    So first, create a project, upload clks with a token (which should work), and then re-upload clks using the same
    token which should return a 403 error.
    """
    expected_number_parties = get_expected_number_parties(valid_project_params)
    if expected_number_parties < 2:
        # The test is not made for less than two parties
        return

    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    update_tokens = new_project_data['update_tokens']

    assert len(update_tokens) == expected_number_parties

    small_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_128B_1k.bin')
    token_to_reuse = update_tokens[0]
    upload_binary_data_from_file(
        requests,
        small_file_path, new_project_data['project_id'], token_to_reuse, 1000)

    upload_binary_data_from_file(
        requests,
        small_file_path, new_project_data['project_id'], token_to_reuse, 1000, expected_status_code=403)


def test_project_upload_invalid_clks_then_valid_clks_same_authentication(requests, valid_project_params):
    """
    Test that a token can be re-used to upload clks after the upload failed.
    So first, create a project, upload clks with a token (which should NOT work with a 400 error),
    and then re-upload clks using the same token which should work.
    """
    expected_number_parties = get_expected_number_parties(valid_project_params)

    new_project_data = requests.post(url + '/projects',
                                     json={
                                         'schema': {},
                                         **valid_project_params
                                     }).json()
    update_tokens = new_project_data['update_tokens']

    assert len(update_tokens) == expected_number_parties

    small_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'testdata/clks_128B_1k.bin')
    token_to_reuse = update_tokens[0]
    # This should fail as we are not providing the good count.
    upload_binary_data_from_file(
        requests,
        small_file_path, new_project_data['project_id'], token_to_reuse, 2000, expected_status_code=400)

    upload_binary_data_from_file(
        requests,
        small_file_path, new_project_data['project_id'], token_to_reuse, 1000)
