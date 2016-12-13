import os
import math
import time
import json
import requests

from anonlink import randomnames, entitymatch, bloomfilter, concurrent

from phe import paillier, util
from serialization import *

"""
The URL to test can be overridden with the environment variable
ENTITY_SERVICE_URL

# When running behind ngnix
url = "http://localhost:8851/api/v1"

# When running the flask application directly
set the environment variable ENTITY_SERVICE_URL to "http://localhost:8851"
"""
#url = os.environ.get("ENTITY_SERVICE_URL", "http://localhost:8851/api/v1")
url = os.environ.get("ENTITY_SERVICE_URL", "http://130.155.156.203:8851/api/v1")


def retrieve_result(mapping_id, token):
    print("Retrieving mapping")
    response = requests.get(url + '/mappings/{}'.format(mapping_id),
                            headers={'Authorization': token})
    print(response.status_code)
    #print(response.json())
    return response


def server_status_test():
    print("Connecting to server '{}'".format(url))
    status = requests.get(url + '/status')
    print("Server status:")
    assert status.status_code == 200, 'Server status was {}'.format(status.status_code)
    print(status.json())


def delete_mapping(id):
    print("Delete the mapping + data")
    response_delete = requests.delete(url + '/mappings/{}'.format(id),
                                      # headers={'Authorization': new_map_response['update_tokens'][1]}
                                      )
    print(response_delete)
    print("Servers mappings:")
    mappings_response = requests.get(url + '/mappings').json()
    assert not any(mapping['resource_id'] == id for mapping in mappings_response['mappings'])


def mapping_test(party1_filters, party2_filters, s1, s2):
    """
    Uses the NameList data and schema and a result_type of "mapping"
    """
    dataset_size = len(party1_filters)
    server_status_test()

    print("Servers mappings:")
    print(requests.get(url + '/mappings').json())


    print('Creating a new mapping')
    # ('INDEX', 'NAME freetext', 'DOB YYYY/MM/DD', 'GENDER M or F')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    new_map_response = requests.post(url + '/mappings', json={
        'schema': schema,
        'result_type': 'mapping'
    }).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    print("New mapping request created with id: ", id)

    print("Servers mappings:")
    print(requests.get(url + '/mappings').json())

    print("Checking mapping status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    print(r.status_code, r.json())
    assert r.status_code == 401

    print("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    print(r.status_code, r.json())
    assert r.status_code == 403

    print("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    print(response.status_code)
    assert response.status_code == 404

    print("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    print(r.status_code, r.json())
    assert r.status_code == 503

    print("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    print(resp1.status_code, r1)

    print("Check the server hasn't died")
    server_status_test()

    print("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    print(resp.text)
    assert 'token required' in resp.json()['message']

    print("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        json={},
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    print("Adding second party's data - properly this time")
    party2_data = {'clks': party2_filters}
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201

    print("Going to sleep to give the server some processing time...")
    time.sleep(1)

    response = retrieve_result(id, new_map_response['result_token'])
    while not response.status_code == 200:
        snooze = dataset_size/20000
        #print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, new_map_response['result_token'])

        if response.status_code == 503:
            print(response.json())

    assert response.status_code == 200

    print("Success")
    mapping_result = response.json()["mapping"]
    #print(mapping_result)
    # TODO Actually check the result.
    #delete_mapping(id)


def permutation_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    dataset_size = len(party1_filters)
    print("Servers mappings:")
    print(requests.get(url + '/mappings').json())

    print("Generating paillier keypair")
    pub, priv = paillier.generate_paillier_keypair()
    public_key = {
        "n": util.int_to_base64(pub.n),
        "key_ops": ["encrypt"],
        "kty": "DAJ",
        "alg": "PAI-GN1",
        "kid": "entity-service generated key for testing"
    }

    print('Creating a new mapping')
    # ('INDEX', 'NAME freetext', 'DOB YYYY/MM/DD', 'GENDER M or F')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    new_map_response = requests.post(url + '/mappings', json={
        'schema': schema,
        'result_type': 'permutation',
        'public_key': public_key,
        'paillier_context': {'base': base, 'encoded': True}
    }).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    print("New mapping request created with id: ", id)

    print("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    print(r.status_code, r.json())
    assert r.status_code == 401

    print("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    print(r.status_code, r.json())
    assert r.status_code == 403

    print("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    print(response.status_code)
    assert response.status_code == 404

    print("Checking status with valid results token (not receipt token as required)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    print(r.status_code, r.json())
    assert r.status_code == 403

    print("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    print(resp1.status_code, r1)

    server_status_test()

    print("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    print("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    print("Adding second party's data - properly this time")
    party2_data = {
        'clks': party2_filters
    }
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    print(resp2.status_code, r2)

    print("Going to sleep to give the server some processing time...")
    time.sleep(1)

    print("Retrieving results as organisation 1")
    response = retrieve_result(id, r1['receipt-token'])
    while not response.status_code == 200:
        snooze = dataset_size/200
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response.status_code == 200
    mapping_result_a = response.json()

    print("Retrieving results as organisation 2")
    response = retrieve_result(id, r2['receipt-token'])
    while not response.status_code == 200:
        snooze = 3*dataset_size/1000
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r2['receipt-token'])

    assert response.status_code == 200
    mapping_result_b = response.json()

    #delete_mapping(id)

    # Now we will print a few sample matches...

    for original_a_index, element in enumerate(s1):
        new_index = mapping_result_a['permutation']['permutation'][original_a_index]
        if new_index < 10:
            print(original_a_index, " -> ", new_index, element)

    print("\nOrg 2\n")
    for original_b_index, element in enumerate(s2):
        new_index = mapping_result_b['permutation']['permutation'][original_b_index]
        if new_index < 10:
            # Encrypted mask:
            # mapping_result_b['permutation']['mask']
            print(original_b_index, " -> ", new_index, element)

    print("Decrypting mask used for first 10 entities...")

    class EntityEncodedNumber(paillier.EncodedNumber):
        BASE = base
        LOG2_BASE = math.log(BASE, 2)

    encrypted_mask = [paillier.EncryptedNumber(pub, int(m)) for m in mapping_result_b['permutation']['mask'][:10]]

    decrypted_mask = [priv.decrypt_encoded(e, Encoding=EntityEncodedNumber).decode() for e in encrypted_mask]
    print(decrypted_mask)
    print("Server took {:8.3f} seconds for matching".format(matching_time))


def permutation_unencrypted_mask_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    dataset_size = len(party1_filters)
    print("Servers mappings:")
    print(requests.get(url + '/mappings').json())

    print('Creating a new mapping')
    # ('INDEX', 'NAME freetext', 'DOB YYYY/MM/DD', 'GENDER M or F')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    new_map_response = requests.post(url + '/mappings', json={
        'schema': schema,
        'result_type': 'permutation_unencrypted_mask'
    }).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    result_token = new_map_response['result_token']
    print("New mapping request created with id: ", id)

    print("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    print(r.status_code, r.json())
    assert r.status_code == 401

    print("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    print(r.status_code, r.json())
    assert r.status_code == 403

    print("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    print(response.status_code)
    assert response.status_code == 404

    print("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    print(r.status_code, r.json())
    assert r.status_code == 503

    print("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    print(resp1.status_code, r1)

    server_status_test()

    print("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    print("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    print("Adding second party's data - properly this time")
    party2_data = {
        'clks': party2_filters
    }
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    print(resp2.status_code, r2)

    print("Going to sleep to give the server some processing time...")
    time.sleep(1)

    print("Retrieving results as organisation 1")
    response_org1 = retrieve_result(id, r1['receipt-token'])
    while not response_org1.status_code == 200:
        snooze = dataset_size/200
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org1 = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response_org1.status_code == 200
    mapping_result_a = response_org1.json()
    print(mapping_result_a)

    print("Retrieving results as organisation 2")
    response_org2 = retrieve_result(id, r2['receipt-token'])
    while not response_org2.status_code == 200:
        snooze = 3*dataset_size/1000
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org2 = retrieve_result(id, r2['receipt-token'])

    assert response_org2.status_code == 200
    mapping_result_b = response_org2.json()
    print(mapping_result_b)

    print("Retrieving results as coordinator")
    response_coordinator = retrieve_result(id, result_token)
    while not response_coordinator.status_code == 200:
        snooze = 3*dataset_size/1000
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_coordinator = retrieve_result(id, result_token)

    assert response_coordinator.status_code == 200
    mask = json.loads(response_coordinator.json()['permutation_unencrypted_mask'])['mask']
    print(response_coordinator.json())

    #delete_mapping(id)

    # Now we will print a few sample matches...

    for original_a_index, element in enumerate(s1):
        new_index = mapping_result_a['permutation_unencrypted_mask'][original_a_index]
        if new_index < 10:
            print(original_a_index, " -> ", new_index, element)

    print("\nOrg 2\n")
    for original_b_index, element in enumerate(s2):
        new_index = mapping_result_b['permutation_unencrypted_mask'][original_b_index]
        if new_index < 10:
            print(original_b_index, " -> ", new_index, element)

    print("\nCoordinator\n")
    print(mask[:10])
    print("Server took {:8.3f} seconds for matching".format(matching_time))


def generate_test_data(dataset_size=1000):
    print("Generating local address data")
    nl = randomnames.NameList(math.floor(dataset_size * 1.2))
    s1, s2 = nl.generate_subsets(dataset_size, 0.8)

    # s2 = s2[:10]

    print("Locally hashing party A identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = concurrent.bloom_filters(s1, nl.schema, keys)

    print("Locally hashing party B identity data to create bloom filters")
    filters2 = concurrent.bloom_filters(s2, nl.schema, keys)

    print("Serialising bloom filters")
    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)

    return party1_filters, party2_filters, s1, s2


def delete_all_mappings():
    mappings = requests.get(url + '/mappings').json()['mappings']
    for mapping in mappings:
        delete_mapping(mapping['resource_id'])


def timing_test(outfile=None):
    test_sizes = [
        5000,
        10000,
        20000,
        50000,
        100000
    ]

    party1_filters, party2_filters, s1, s2 = generate_test_data(test_sizes[-1])

    results = {}
    for size in test_sizes:
        print("Running e2e test with {} entites".format(size))

        start = time.time()

        #permutation_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])

        mapping_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
        elapsed = time.time() - start

        results[size] = elapsed
        print(
            "Permutation test with {} entities complete after {:.3f} seconds".format(size, elapsed),
            file=outfile)

if __name__ == "__main__":

    size = int(os.environ.get("ENTITY_SERVICE_TEST_SIZE", "100"))
    repeats = int(os.environ.get("ENTITY_SERVICE_TEST_REPEATS", "1"))
    do_timing = os.environ.get("ENTITY_SERVICE_TIMING_TEST", None) is not None
    do_delete_all = os.environ.get("ENTITY_SERVICE_DELETE_ALL", None) is not None
    do_permutation_test = os.environ.get("ENTITY_SERVICE_PERMUTATION", None) is not None

    server_status_test()

    if do_timing:
        with open("timing-results.txt", "at") as f:
            timing_test(f)
    elif do_delete_all:
        delete_all_mappings()
    else:

        party1_filters, party2_filters, s1, s2 = generate_test_data(size)

        mapping_times = []
        permutation_times = []

        for i in range(repeats):
            mapping_start = time.time()
            mapping_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
            mapping_times.append(time.time() - mapping_start)

        if do_permutation_test:
            for i in range(repeats):
                perm_start = time.time()
                permutation_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
                permutation_times.append(time.time() - perm_start)
            print("---> Permutation test took an average of {:.3f} seconds".format(sum(permutation_times)/repeats))

        print("---> Mapping test took an average of {:.3f} seconds".format(sum(mapping_times)/repeats))
        print("---> Number of entities: {}".format(size))

        # permutation_unencrypted_mask_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])