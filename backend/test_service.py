import os, sys
import math
import time
import json
import logging
import requests

from anonlink import randomnames, entitymatch, bloomfilter, concurrent

from phe import paillier, util
from serialization import *

LOGLEVEL = getattr(logging, os.environ.get("LOGGING_LEVEL", "WARNING"))
logger = logging.getLogger('n1')
logger.setLevel(LOGLEVEL)
formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(levelname)s - %(message)s', "%H:%M:%S")
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.propagate = False
logger.addHandler(ch)

"""
The URL to test can be overridden with the environment variable
ENTITY_SERVICE_URL

# When running behind ngnix
url = "http://localhost:8851/api/v1"

# When running the flask application directly
set the environment variable ENTITY_SERVICE_URL to "http://localhost:8851"
"""
url = os.environ.get("ENTITY_SERVICE_URL", "http://localhost:8851/api/v1")
logger.info("Entity Service URL: {}".format(url))


def retrieve_result(mapping_id, token):
    logger.info("Retrieving mapping")
    response = requests.get(url + '/mappings/{}'.format(mapping_id),
                            headers={'Authorization': token})
    logger.debug(response.status_code)
    #logger.debug(response.json())
    return response


def server_status_test():
    logger.debug("Connecting to server '{}'".format(url))
    status = requests.get(url + '/status')
    logger.debug("Server status:")
    assert status.status_code == 200, 'Server status was {}'.format(status.status_code)
    logger.debug(status.json())
    version = requests.get(url + '/version')
    logger.info(version.text)


def delete_mapping(id):
    logger.info("Delete the mapping + data")
    response_delete = requests.delete(url + '/mappings/{}'.format(id),
                                      # headers={'Authorization': new_map_response['update_tokens'][1]}
                                      )
    logger.debug(response_delete)
    logger.debug("Servers mappings:")
    mappings_response = requests.get(url + '/mappings').json()
    assert not any(mapping['resource_id'] == id for mapping in mappings_response['mappings'])


def mapping_test(party1_filters, party2_filters, s1, s2):
    """
    Uses the NameList data and schema and a result_type of "mapping"
    """
    dataset_size = len(party1_filters)
    server_status_test()

    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings').json())

    logger.info('Creating a new mapping')
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
    logger.debug(new_map_response)

    id = new_map_response['resource_id']
    logger.info("New mapping request created with id: {}".format(id))

    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings').json())

    logger.info("Checking mapping status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    logger.info("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    logger.info("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 404

    logger.info("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 503

    logger.info("Adding first party's filter data")

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
    logger.debug(resp1.status_code, r1)

    logger.info("Check the server hasn't died")
    server_status_test()

    logger.info("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    logger.debug(resp.text)
    assert 'token required' in resp.json()['message']

    logger.info("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        json={},
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    logger.info("Adding second party's data - properly this time")
    party2_data = {'clks': party2_filters}
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    response = retrieve_result(id, new_map_response['result_token'])
    while not response.status_code == 200:
        snooze = 5 + dataset_size/20000
        #logger.debug("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, new_map_response['result_token'])

        if response.status_code == 503:
            logger.debug(response.json())

    assert response.status_code == 200

    logger.info("Success")
    mapping_result = response.json()["mapping"]
    #logger.debug(mapping_result)
    # TODO Actually check the result.
    #delete_mapping(id)


def permutation_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    dataset_size = len(party1_filters)
    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings').json())

    logger.info("Generating paillier keypair")
    pub, priv = paillier.generate_paillier_keypair()
    public_key = {
        "n": util.int_to_base64(pub.n),
        "key_ops": ["encrypt"],
        "kty": "DAJ",
        "alg": "PAI-GN1",
        "kid": "entity-service generated key for testing"
    }

    logger.info('Creating a new mapping')
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
    logger.debug(new_map_response)

    id = new_map_response['resource_id']
    logger.info("New mapping request created with id: {}".format(id))

    logger.info("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    logger.info("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    logger.info("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 404

    logger.info("Checking status with valid results token (not receipt token as required)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    logger.info("Adding first party's filter data")

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
    logger.debug(resp1.status_code, r1)

    server_status_test()

    logger.info("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    logger.info("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    logger.info("Adding second party's data - properly this time")
    party2_data = {
        'clks': party2_filters
    }
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    logger.debug(resp2.status_code, r2)

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    logger.info("Retrieving results as organisation 1")
    response = retrieve_result(id, r1['receipt-token'])
    while not response.status_code == 200:
        snooze = 5 + dataset_size/200
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response.status_code == 200
    mapping_result_a = response.json()

    logger.info("Retrieving results as organisation 2")
    response = retrieve_result(id, r2['receipt-token'])
    while not response.status_code == 200:
        snooze = 5 + 3*dataset_size/1000
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r2['receipt-token'])

    assert response.status_code == 200
    mapping_result_b = response.json()

    #delete_mapping(id)

    # Now we will print a few sample matches...

    for original_a_index, element in enumerate(s1):
        new_index = int(mapping_result_a['permutation'][original_a_index])
        if new_index < 10:
            logger.info("{} -> {} {}".format(original_a_index, new_index, element))

    logger.info("\nOrg 2\n")
    for original_b_index, element in enumerate(s2):
        new_index = int(mapping_result_b['permutation'][original_b_index])
        if new_index < 10:
            # Encrypted mask:
            # mapping_result_b['permutation']['mask']
            logger.info("{} -> {} {}".format(original_b_index, new_index, element))

    logger.info("Decrypting mask used for first 10 entities...")

    class EntityEncodedNumber(paillier.EncodedNumber):
        BASE = base
        LOG2_BASE = math.log(BASE, 2)

    encrypted_mask = [paillier.EncryptedNumber(pub, phe.util.base64_to_int(m)) for m in mapping_result_b['mask'][:10]]

    decrypted_mask = [priv.decrypt_encoded(e, Encoding=EntityEncodedNumber).decode() for e in encrypted_mask]
    logger.info(decrypted_mask)
    logger.info("Server took {:8.3f} seconds for matching".format(matching_time))


def permutation_unencrypted_mask_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    dataset_size = len(party1_filters)
    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings').json())

    logger.info('Starting permutation_unencrypted_mask_test')
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
    logger.debug(new_map_response)

    id = new_map_response['resource_id']
    result_token = new_map_response['result_token']
    logger.info("New mapping request created with id: {}".format(id))

    logger.info("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id))
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    logger.info("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    logger.info("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 404

    logger.info("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 503

    logger.info("Adding first party's filter data")

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
    logger.debug(resp1.status_code, r1)

    server_status_test()

    logger.info("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    logger.info("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    logger.info("Adding second party's data - properly this time")
    party2_data = {
        'clks': party2_filters
    }
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    logger.debug(resp2.status_code, r2)

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    logger.info("Retrieving results as organisation 1")
    response_org1 = retrieve_result(id, r1['receipt-token'])
    while not response_org1.status_code == 200:
        snooze = 5
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org1 = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response_org1.status_code == 200
    mapping_result_a = response_org1.json()
    logger.info("Mapping from org 1: {}".format(mapping_result_a))

    logger.info("Retrieving results as organisation 2")
    response_org2 = retrieve_result(id, r2['receipt-token'])
    while not response_org2.status_code == 200:
        snooze = 5
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org2 = retrieve_result(id, r2['receipt-token'])

    assert response_org2.status_code == 200
    mapping_result_b = response_org2.json()
    logger.info("Mapping from org 2: {}".format(mapping_result_b))

    logger.info("Retrieving results as coordinator")
    response_coordinator = retrieve_result(id, result_token)
    while not response_coordinator.status_code == 200:
        snooze = 5
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_coordinator = retrieve_result(id, result_token)
    logger.info("Mapping from coordinator: {}".format(response_coordinator.json()))

    assert response_coordinator.status_code == 200
    mask = response_coordinator.json()['mask']
    logger.debug(response_coordinator.json())

    #delete_mapping(id)

    # Now we will print a few sample matches...

    for original_a_index, element in enumerate(s1):
        new_index = int(mapping_result_a['permutation'][original_a_index])
        if new_index < 10:
            logger.info("{} -> {} {}".format(original_a_index, new_index, element))

    logger.info("\nOrg 2\n")
    for original_b_index, element in enumerate(s2):
        new_index = int(mapping_result_b['permutation'][original_b_index])
        if new_index < 10:
            logger.info("{} -> {} {}".format(original_b_index, new_index, element))

    logger.info("\nCoordinator\n")
    logger.info(mask[:10])
    logger.info("Server took {:8.3f} seconds for matching".format(matching_time))


def generate_test_data(dataset_size=1000):
    logger.info("Generating local address data")
    nl = randomnames.NameList(math.floor(dataset_size * 1.2))
    s1, s2 = nl.generate_subsets(dataset_size, 0.8)

    logger.info("Locally hashing party A identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = concurrent.bloom_filters(s1, nl.schema, keys)

    logger.info("Locally hashing party B identity data to create bloom filters")
    filters2 = concurrent.bloom_filters(s2, nl.schema, keys)

    logger.info("Serialising bloom filters")
    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)
    logger.info("Data generation complete")
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
    logger.warning("Generating test data. This may take some time.")
    party1_filters, party2_filters, s1, s2 = generate_test_data(test_sizes[-1])

    results = {}
    for size in test_sizes:
        logger.info("Running e2e test with {} entites".format(size))

        start = time.time()

        # Switch method if more interested in the encrypted or non masked versions:
        #permutation_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
        #mapping_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
        permutation_unencrypted_mask_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])

        elapsed = time.time() - start

        results[size] = elapsed
        print(
            "Permutation test with {} entities complete after {:.3f} seconds".format(size, elapsed),
            file=outfile)


class Timer:
    def __enter__(self):
        self.start = time.clock()
        return self

    def __exit__(self, *args):
        self.end = time.clock()
        self.interval = self.end - self.start

if __name__ == "__main__":

    size = int(os.environ.get("ENTITY_SERVICE_TEST_SIZE", "1000"))
    repeats = int(os.environ.get("ENTITY_SERVICE_TEST_REPEATS", "1"))
    do_timing = os.environ.get("ENTITY_SERVICE_TIMING_TEST", None) is not None
    do_delete_all = os.environ.get("ENTITY_SERVICE_DELETE_ALL", None) is not None
    do_permutation_test = os.environ.get("ENTITY_SERVICE_PERMUTATION", None) is not None

    server_status_test()

    if do_timing:
        logger.info("Carrying out timing benchmark")
        timing_test()
    elif do_delete_all:
        logger.warning("Deleting all mapping data")
        delete_all_mappings()
    else:
        logger.info("Carrying out e2e test")
        print("---> Number of entities: {}".format(size))
        party1_filters, party2_filters, s1, s2 = generate_test_data(size)

        mapping_times = []
        permutation_times = []

        for i in range(repeats):
            with Timer() as mapping_timer:
                mapping_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
            mapping_times.append(mapping_timer.interval)

        if do_permutation_test:
            logger.info("Doing permutation with encrypted mask test")
            for i in range(repeats):
                with Timer() as perm_timer:
                    permutation_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
                permutation_times.append(perm_timer.interval)
            print("---> Permutation (encrypted) test took an average of {:.3f} seconds".format(sum(permutation_times)/repeats))

        print("---> Mapping test took an average of {:.3f} seconds".format(sum(mapping_times)/repeats))

        with Timer() as t:
            permutation_unencrypted_mask_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
        print("---> Permutation (unencrypted) test took {:.3f} seconds".format(t.interval))
