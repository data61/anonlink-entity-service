import io
import json
import time
import os
import pytest
from minio import Minio

from e2etests.config import url, minio_host
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


def test_project_upload_external_encodings(requests, a_project, binary_test_file_path):

    mc, upload_info = get_temp_upload_client(a_project, requests, a_project['update_tokens'][0])

    etag = mc.fput_object(
        upload_info['bucket'],
        upload_info['path'] + "/test",
        binary_test_file_path,
        metadata={
            "hash-count": 1000,
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


def test_project_upload_external_data_binary(requests, a_blocking_project, binary_test_file_path):
    project = a_blocking_project
    blocking_data = json.dumps(
        {"blocks": {str(encoding_id): list({str(encoding_id % 3), str(encoding_id % 13)}) for encoding_id in range(1000)}}).encode()

    mc, upload_info = get_temp_upload_client(project, requests, project['update_tokens'][0])

    _upload_encodings_and_blocks_binary(mc, upload_info, blocking_data, binary_test_file_path)

    # Should be able to notify the service that we've uploaded data
    res = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][0]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/encodings",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/blocks",
                                }
                            }

                        }
                       )
    assert res.status_code == 201

    # If the second data provider uses the same path to upload data, that shouldn't work
    res2 = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][1]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/encodings",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/blocks",
                                }
                            }

                        }
                       )
    assert res2.status_code == 403

    mc2, upload_info2 = get_temp_upload_client(project, requests, project['update_tokens'][1])
    _upload_encodings_and_blocks_binary(mc2, upload_info2, blocking_data, binary_test_file_path)

    # If the second data provider uses the correct path to upload data, that should work
    res3 = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][1]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info2['bucket'],
                                    'path': upload_info2['path'] + "/encodings",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info2['bucket'],
                                    'path': upload_info2['path'] + "/blocks",
                                }
                            }
                        }
                       )
    assert res3.status_code == 201
    run_id = post_run(requests, project, threshold=0.95)
    result = get_run_result(requests, project, run_id, timeout=240)
    assert 'groups' in result


def test_project_upload_external_data_json(requests, a_blocking_project, binary_test_file_path):
    project = a_blocking_project
    blocking_data = json.dumps(
        {"blocks": {str(encoding_id): list({str(encoding_id % 3), str(encoding_id % 13)}) for encoding_id in range(1000)}}).encode()

    clks_data = json.dumps({"clks": ['ssssssss'] * 1000}).encode()
    mc, upload_info = get_temp_upload_client(project, requests, project['update_tokens'][0])

    _upload_encodings_and_blocks_json(mc, upload_info, blocking_data, clks_data)

    # Should be able to notify the service that we've uploaded data
    res = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][0]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/encodings.json",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/blocks",
                                }
                            }

                        }
                       )
    assert res.status_code == 201

    # If the second data provider uses the same path to upload data, that shouldn't work
    res2 = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][1]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/encodings.json",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info['bucket'],
                                    'path': upload_info['path'] + "/blocks",
                                }
                            }

                        }
                       )
    assert res2.status_code == 403

    mc2, upload_info2 = get_temp_upload_client(project, requests, project['update_tokens'][1])
    _upload_encodings_and_blocks_json(mc2, upload_info2, blocking_data, clks_data)

    # If the second data provider uses the correct path to upload data, that should work
    res3 = requests.post(url + f"projects/{project['project_id']}/clks",
                        headers={'Authorization': project['update_tokens'][1]},
                        json={
                            'encodings': {
                                'file': {
                                    'bucket': upload_info2['bucket'],
                                    'path': upload_info2['path'] + "/encodings.json",
                                }
                            },
                            'blocks': {
                                'file': {
                                    'bucket': upload_info2['bucket'],
                                    'path': upload_info2['path'] + "/blocks",
                                }
                            }
                        }
                       )
    assert res3.status_code == 201
    run_id = post_run(requests, project, threshold=0.95)
    result = get_run_result(requests, project, run_id, timeout=240)
    assert 'groups' in result


def _upload_encodings_and_blocks_binary(mc, upload_info, blocking_data, binary_test_file_path):
    mc.fput_object(
        upload_info['bucket'],
        upload_info['path'] + "/encodings",
        binary_test_file_path,
        metadata={
            "hash-count": 1000,
            "hash-size": 8
        }
    )
    mc.put_object(
        upload_info['bucket'],
        upload_info['path'] + "/blocks",
        io.BytesIO(blocking_data),
        len(blocking_data)
    )


def _upload_encodings_and_blocks_json(mc, upload_info, blocking_data, clks_data):
    mc.put_object(
        upload_info['bucket'],
        upload_info['path'] + "/encodings.json",
        io.BytesIO(clks_data),
        metadata={
            "hash-count": 1000,
            "hash-size": 8
        },
        length=len(clks_data)
    )
    mc.put_object(
        upload_info['bucket'],
        upload_info['path'] + "/blocks",
        io.BytesIO(blocking_data),
        len(blocking_data)
    )


def get_temp_upload_client(project, requests, update_token):
    r = requests.get(
        url + 'projects/{}/authorize-external-upload'.format(project['project_id']),
        headers={'Authorization': update_token},
    )
    assert r.status_code == 201
    upload_response = r.json()
    credentials = upload_response['credentials']
    upload_info = upload_response['upload']
    mc = Minio(
        minio_host or upload_info['endpoint'],
        access_key=credentials['AccessKeyId'],
        secret_key=credentials['SecretAccessKey'],
        session_token=credentials['SessionToken'],
        region='us-east-1',
        secure=upload_info['secure']
    )
    return mc, upload_info


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
    result = get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)

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
    result = get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)
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
    result = get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)
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
        get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)


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
        get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)


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
        get_run_result(requests, new_project_data, run_id, wait=True, timeout=240)


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
