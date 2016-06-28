import os
import math
import time
import requests
from anonlink import randomnames, entitymatch
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
url = os.environ.get("ENTITY_SERVICE_URL", "http://localhost:8851/api/v1")


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


def mapping_test(dataset_size=1000):
    """
    Uses the NameList data and schema and a result_type of "mapping"
    """
    print("Connecting to server '{}'".format(url))
    status = requests.get(url + '/status')
    print("Server status:")
    assert status.status_code == 200, 'Server status was {}'.format(status.status_code)
    print(status.json())

    print('*'*80)
    print("Running e2e test with {} entites".format(dataset_size))
    print("Generating local address data")
    nl = randomnames.NameList(dataset_size * 2)
    s1, s2 = nl.generate_subsets(dataset_size, 0.8)

    print("Locally hashing identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = entitymatch.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = entitymatch.calculate_bloom_filters(s2, nl.schema, keys)

    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)

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
        snooze = 30*dataset_size/10000
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, new_map_response['result_token'])

    assert response.status_code == 200

    mapping_result = response.json()["mapping"]
    print(mapping_result)

    delete_mapping(id)


def permutation_test(dataset_size=500, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """

    print("Running e2e test with {} entites".format(dataset_size))
    print("Generating local address data")
    nl = randomnames.NameList(dataset_size * 2)
    s1, s2 = nl.generate_subsets(dataset_size, 0.8)


    #s2 = s2[:10]

    print("Locally hashing identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = entitymatch.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = entitymatch.calculate_bloom_filters(s2, nl.schema, keys)

    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)

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

    delete_mapping(id)

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


def timing_test(outfile=None):
    results = {}
    for size in [
            10, 100, 200, 500, 1000, 2000, 5000,
            #10000, 20000
            #50000,
            #100000
            ]:
        start = time.time()
        permutation_test(size)
        elapsed = time.time() - start

        results[size] = elapsed
        print(
            "Permutation test with {} entities complete after {:.3f} seconds".format(size, elapsed),
            file=outfile)


if __name__ == "__main__":
    size = int(os.environ.get("ENTITY_SERVICE_TEST_SIZE", "500"))
    repeats = int(os.environ.get("ENTITY_SERVICE_TEST_REPEATS", "1"))
    do_timing = os.environ.get("ENTITY_SERVICE_TIMING_TEST", None) is not None

    server_status_test()

    if do_timing:
        with open("timing-results.txt", "at") as f:
            timing_test(f)
    else:
        for i in range(repeats):
            mapping_start = time.time()
            mapping_test(size)
            mapping_end = time.time()

        for i in range(repeats):
            perm_start = time.time()
            permutation_test(size)
            perm_end = time.time()

        print("---> Mapping test complete after {:.3f} seconds".format(mapping_end - mapping_start))
        print("---> Permutation test with {} entities complete after {:.3f} seconds".format(size, perm_end - perm_start))
