"""
A script to test a deployed entity service.

"""


import os, sys
import math
import time
import json
import logging
import requests
import unittest

from clkhash import randomnames, clk
from clkhash.bloomfilter import calculate_bloom_filters
from clkhash.key_derivation import generate_key_lists
from clkhash.schema import get_schema_types

from phe import paillier, util
from serialization import *
from tests.util import serialize_bitarray, serialize_filters, logger, initial_delay, rate_limit_delay

http_request_timeout = float(os.environ.get("REQUEST_TIMEOUT", "5"))

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
    logger.debug("Retrieving mapping")
    response = requests.get(url + '/mappings/{}'.format(mapping_id),
                            timeout=http_request_timeout,
                            headers={'Authorization': token})
    logger.debug(response.status_code)
    return response


def server_status_test():
    logger.debug("Connecting to server '{}'".format(url))
    status = requests.get(url + '/status', timeout=http_request_timeout)
    logger.debug("Server status:")
    assert status.status_code == 200, 'Server status was {}'.format(status.status_code)
    logger.debug(status.json())
    # Small sleep to avoid hitting rate limits while testing
    time.sleep(rate_limit_delay)
    version = requests.get(url + '/version', timeout=http_request_timeout)
    logger.debug(version.text)
    time.sleep(rate_limit_delay)


def delete_mapping(id):
    logger.debug("Deleting mapping")
    response_delete = requests.delete(url + '/mappings/{}'.format(id),
                                      timeout=http_request_timeout,
                                      # headers={'Authorization': new_map_response['update_tokens'][1]}
                                      )
    logger.debug(response_delete)
    time.sleep(0.05)

    mappings_response = requests.get(url + '/mappings', timeout=http_request_timeout).json()
    assert not any(mapping['resource_id'] == id for mapping in mappings_response['mappings'])


def mapping_test(party1_filters, party2_filters, s1, s2):
    """
    Uses the NameList data and schema and a result_type of "mapping"
    """
    logger = logging.getLogger('n1.mappingtest')
    dataset_size = len(party1_filters)
    logger.info("Starting mapping test with dataset size {}".format(dataset_size))
    server_status_test()

    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings', timeout=http_request_timeout).json())

    logger.info('Creating a new mapping')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    new_map_response = requests.post(url + '/mappings', timeout=http_request_timeout, json={
        'schema': schema,
        'result_type': 'mapping',
        'threshold': 0.995
    }).json()
    logger.debug(new_map_response)

    id = new_map_response['resource_id']
    logger.debug("New mapping request created with id: {}".format(id))

    logger.debug("Checking mapping status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id), timeout=http_request_timeout)
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    time.sleep(rate_limit_delay)

    logger.info("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     timeout=http_request_timeout,
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    time.sleep(rate_limit_delay)

    logger.debug("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 403

    time.sleep(rate_limit_delay)

    logger.debug("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 503

    logger.info("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})

    # status code should be 201 if a resource was created
    logger.debug("Response code {}".format(resp1.status_code))
    logger.debug("Response\n{}".format(resp1.text))
    assert resp1.status_code == 201, resp1.text

    r1 = resp1.json()
    assert 'receipt-token' in r1
    logger.debug(resp1.status_code, r1)

    logger.debug("Check the server hasn't died")
    server_status_test()

    logger.debug("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), timeout=http_request_timeout, json=party2_data)
    assert resp.status_code == 401
    logger.debug(resp.text)
    assert 'token required' in resp.json()['message']

    logger.debug("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        timeout=http_request_timeout,
                        json={},
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    logger.debug("Adding second party's data - properly this time")
    party2_data = {'clks': party2_filters}
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    response = retrieve_result(id, new_map_response['result_token'])
    while not response.status_code == 200:
        snooze = 5 + dataset_size/20000
        #logger.debug("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze + rate_limit_delay)
        response = retrieve_result(id, new_map_response['result_token'])

        if response.status_code == 503:
            logger.debug(response.json())

    assert response.status_code == 200

    logger.debug("Success")
    mapping_result = response.json()["mapping"]

    # Now actually check the results
    correct_matches, incorrect_matches = 0, 0
    for indx, i in enumerate(mapping_result):
        j = mapping_result[i]
        if indx < 10:
            print(i, j, s1[int(i)], s2[int(j)])

        for a, b in zip(s1[int(i)], s2[int(j)]):
            if a == b:
                correct_matches += 1
            else:
                incorrect_matches += 1

    print("Number matches correct: {}".format(correct_matches))
    print("Number matches incorrect: {}".format(incorrect_matches))
    assert correct_matches > len(s1)//2
    assert incorrect_matches == 0

    # Delete a mapping
    delete_mapping(id)


def similarity_score_test(party1_filters, party2_filters, s1, s2):
    logger = logging.getLogger('n1.similarityscores')
    dataset_size = len(party1_filters)
    server_status_test()

    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings', timeout=http_request_timeout).json())

    logger.debug('Creating a new mapping')
    # ('INDEX', 'NAME freetext', 'DOB YYYY/MM/DD', 'GENDER M or F')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    threshold = 0.995
    new_map_response = requests.post(url + '/mappings', timeout=http_request_timeout, json={
        'schema': schema,
        'result_type': 'similarity_scores',
        'threshold': threshold
    }).json()
    logger.info(new_map_response)

    id = new_map_response['resource_id']
    logger.debug("New mapping request created with id: {}".format(id))


    logger.info("Checking mapping status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id), timeout=http_request_timeout)
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    time.sleep(rate_limit_delay)

    logger.info("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     timeout=http_request_timeout,
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    time.sleep(rate_limit_delay)

    logger.info("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 403

    time.sleep(rate_limit_delay)

    logger.info("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 503

    logger.debug("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         json=party1_data,
                         timeout=http_request_timeout,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    logger.debug(resp1.status_code, r1)

    logger.debug("Check the server hasn't died")
    server_status_test()

    logger.debug("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), timeout=http_request_timeout, json=party2_data)
    assert resp.status_code == 401
    logger.debug(resp.text)
    assert 'token required' in resp.json()['message']

    logger.debug("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        timeout=http_request_timeout,
                        json={},
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    logger.debug("Adding second party's data - properly this time")
    party2_data = {'clks': party2_filters}
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    logger.debug("Retrieving similarity scores")
    response = retrieve_result(id, new_map_response['result_token'])

    while not response.status_code == 200:
        snooze = 5 + dataset_size/20000
        #logger.debug("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze + rate_limit_delay)
        response = retrieve_result(id, new_map_response['result_token'])

        if response.status_code == 503:
            logger.debug(response.json())

    assert response.status_code == 200

    logger.info("Success")

    similarity_scores = response.json()["similarity_scores"]

    # Check the scores in the results are correct
    for score in similarity_scores:
        assert score[2] > threshold

    # Delete a mapping
    #delete_mapping(id)


def permutation_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    logger = logging.getLogger('n1.permutationtest')
    dataset_size = len(party1_filters)
    dataset_size_2 = len(party2_filters)
    logger.info("Carrying out permutation test with dataset size {} x {}".format(dataset_size, dataset_size_2))
    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings', timeout=http_request_timeout).json())

    logger.info("Generating paillier keypair")
    pub, priv = paillier.generate_paillier_keypair()
    public_key = {
        "n": util.int_to_base64(pub.n),
        "key_ops": ["encrypt"],
        "kty": "DAJ",
        "alg": "PAI-GN1",
        "kid": "entity-service generated key for testing"
    }

    logger.debug('Creating a new permutation mapping')
    # ('INDEX', 'NAME freetext', 'DOB YYYY/MM/DD', 'GENDER M or F')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    r = requests.post(url + '/mappings', json={
        'schema': schema,
        'threshold': 0.6,
        'result_type': 'permutation',
        'public_key': public_key,
        'paillier_context': {'base': base, 'encoded': True}
    })
    logger.debug(r.text)
    new_map_response = r.json()

    id = new_map_response['resource_id']
    logger.debug("New mapping request created with id: {}".format(id))

    time.sleep(rate_limit_delay)

    logger.debug("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id), timeout=http_request_timeout)
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    time.sleep(rate_limit_delay)

    logger.debug("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     timeout=http_request_timeout,
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    time.sleep(rate_limit_delay)

    logger.debug("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 403

    time.sleep(rate_limit_delay)

    logger.debug("Checking status with valid results token (not receipt token as required)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    logger.info("Uploading first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    logger.debug(resp1.status_code, r1)

    server_status_test()

    logger.debug("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    resp = requests.put(url + '/mappings/{}'.format(id), timeout=http_request_timeout, json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    logger.debug("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        timeout=http_request_timeout,
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    logger.info("Uploading second party's data")
    party2_data = {
        'clks': party2_filters
    }
    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    logger.debug(resp2.status_code, r2)

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    logger.info("Waiting for computation to complete")
    logger.debug("Retrieving results as organisation 1")
    response = retrieve_result(id, r1['receipt-token'])
    while not response.status_code == 200:
        snooze = 5 + dataset_size/200
        logger.debug("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response.status_code == 200
    mapping_result_a = response.json()

    logger.info("Results retrieved")

    logger.debug("Retrieving results as organisation 2")
    response = retrieve_result(id, r2['receipt-token'])
    while not response.status_code == 200:
        snooze = 5 + 3*dataset_size/1000
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result(id, r2['receipt-token'])

    assert response.status_code == 200
    mapping_result_b = response.json()

    # Now we will log a few sample matches...
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
    logger.info("Server took {:8.3f} seconds for matching with encrypted mask".format(matching_time))


def permutation_unencrypted_mask_test(party1_filters, party2_filters, s1, s2, base=2):
    """
    Uses the NameList data and schema and a result_type of "permutation"
    """
    logger = logging.getLogger('n1.permutation_unenc')
    dataset_size = len(party1_filters)
    logger.debug("Servers mappings:")
    logger.debug(requests.get(url + '/mappings', timeout=http_request_timeout).json())

    logger.debug('Starting permutation_unencrypted_mask_test')
    schema = [
        {"identifier": "INDEX",          "weight": 0, "notes":""},
        {"identifier": "NAME freetext",  "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F",  "weight": 1, "notes": ""}
    ]
    new_map_response = requests.post(url + '/mappings',
                                     timeout=http_request_timeout,
                                     json={
                                         'schema': schema,
                                         'threshold': 0.98,
                                         'result_type': 'permutation_unencrypted_mask'
                                     }).json()
    logger.debug(new_map_response)

    time.sleep(0.25)

    id = new_map_response['resource_id']
    result_token = new_map_response['result_token']
    logger.debug("New mapping request created with id: {}".format(id))

    logger.debug("Checking status without authentication token")
    r = requests.get(url + '/mappings/{}'.format(id), timeout=http_request_timeout)
    logger.debug(r.status_code, r.json())
    assert r.status_code == 401

    time.sleep(0.25)

    logger.debug("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id),
                     timeout=http_request_timeout,
                     headers={'Authorization': 'invalid'})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 403

    time.sleep(0.25)

    logger.debug("Test a mapping that doesn't exist with valid token")
    response = requests.get(
        url + '/mappings/NOT_A_REAL_MAPPING',
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(response.status_code)
    assert response.status_code == 403

    time.sleep(rate_limit_delay)

    logger.info("Checking status with valid token (before adding data)")
    r = requests.get(
        url + '/mappings/{}'.format(id),
        timeout=http_request_timeout,
        headers={'Authorization': new_map_response['result_token']})
    logger.debug(r.status_code, r.json())
    assert r.status_code == 503

    time.sleep(rate_limit_delay)

    logger.debug("Adding first party's filter data")

    party1_data = {
        'clks': party1_filters
    }

    time.sleep(rate_limit_delay)

    resp1 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party1_data,
                         headers={'Authorization': new_map_response['update_tokens'][0]})
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    r1 = resp1.json()
    assert 'receipt-token' in r1
    logger.debug(resp1.status_code, r1)

    server_status_test()

    logger.debug("Adding second party's data - without authentication")
    party2_data = {'clks': party2_filters}
    time.sleep(rate_limit_delay)
    resp = requests.put(url + '/mappings/{}'.format(id), timeout=http_request_timeout, json=party2_data)
    assert resp.status_code == 401
    assert 'token required' in resp.json()['message']

    time.sleep(rate_limit_delay)

    logger.debug("Adding second party's data - without clk data")
    resp = requests.put(url + '/mappings/{}'.format(id),
                        timeout = http_request_timeout,
                        headers={'Authorization': new_map_response['update_tokens'][1]})
    assert resp.status_code == 400
    assert 'Missing information' in resp.json()['message']

    matching_start = time.time()
    logger.debug("Adding second party's data - properly this time")

    resp2 = requests.put(url + '/mappings/{}'.format(id),
                         timeout=http_request_timeout,
                         json=party2_data,
                         headers={'Authorization': new_map_response['update_tokens'][1]})

    assert resp2.status_code == 201
    r2 = resp2.json()
    logger.debug(resp2.status_code, r2)

    logger.debug("Going to sleep to give the server some processing time...")
    time.sleep(1)

    logger.debug("Retrieving results as organisation 1")
    response_org1 = retrieve_result(id, r1['receipt-token'])
    while not response_org1.status_code == 200:
        snooze = 5
        logger.info("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org1 = retrieve_result(id, r1['receipt-token'])

    matching_time = time.time() - matching_start
    assert response_org1.status_code == 200
    mapping_result_a = response_org1.json()
    logger.debug("Mapping from org 1: {}".format(mapping_result_a))

    logger.debug("Retrieving results as organisation 2")
    response_org2 = retrieve_result(id, r2['receipt-token'])
    while not response_org2.status_code == 200:
        snooze = 5
        logger.debug("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response_org2 = retrieve_result(id, r2['receipt-token'])

    assert response_org2.status_code == 200
    mapping_result_b = response_org2.json()
    logger.debug("Mapping from org 2: {}".format(mapping_result_b))

    logger.debug("Retrieving results as coordinator")
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
    logger.info("Server took {:8.3f} seconds for matching with non encrypted permutation".format(matching_time))


def generate_test_data(dataset_size=1000):
    logger.info("Generating local PII data")
    nl = randomnames.NameList(math.floor(dataset_size * 1.3))
    s1, s2 = nl.generate_subsets(dataset_size, 0.8)

    logger.info("Locally hashing party A identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = calculate_bloom_filters(s1, nl.schema_types, generate_key_lists(keys, len(nl.schema_types)))

    logger.info("Locally hashing party B identity data to create bloom filters")
    filters2 = calculate_bloom_filters(s2, nl.schema_types, generate_key_lists(keys, len(nl.schema_types)))

    logger.info("Serialising bloom filters")
    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)

    logger.info("Data generation complete")
    return party1_filters, party2_filters, s1, s2


def delete_all_mappings():
    mappings = requests.get(url + '/mappings', timeout = http_request_timeout).json()['mappings']
    for mapping in mappings:
        delete_mapping(mapping['resource_id'])
        time.sleep(0.05)


def timing_test(outfile=None):
    logger = logging.getLogger('n1.timing')
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
        logger.info(
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

    if initial_delay > 5:
        logger.warning("Waiting {} seconds to allow server to start.".format(initial_delay))
    time.sleep(initial_delay)

    test_start_time = time.time()

    if do_timing:
        logger.info("Carrying out timing benchmark")
        timing_test()
    elif do_delete_all:
        logger.warning("Deleting all mapping data")
        delete_all_mappings()
    else:
        logger.info("Carrying out e2e test")
        logger.info("---> Number of entities: {}".format(size))
        with Timer() as data_generation_timer:
            party1_filters, party2_filters, s1, s2 = generate_test_data(size)

        logger.info("Data generation took {:.3f} seconds".format(data_generation_timer.interval))
        similarity_score_times = []
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
            logger.info("---> Permutation (encrypted) test took an average of {:.3f} seconds".format(sum(permutation_times)/repeats))

        logger.info("---> Mapping test took an average of {:.3f} seconds".format(sum(mapping_times)/repeats))

        with Timer() as t:
            permutation_unencrypted_mask_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
        logger.info("---> Permutation (unencrypted) test took {:.3f} seconds".format(t.interval))

        # Testing similarity score
        for i in range(repeats):
            with Timer() as similarity_score_timer:
                similarity_score_test(party1_filters[:size], party2_filters[:size], s1[:size], s2[:size])
            similarity_score_times.append(similarity_score_timer.interval)
        logger.info("---> Similarity scores test took an average of {:.3f} seconds".format(sum(similarity_score_times)/repeats))

        logger.info("Tests are done after {:.1f} seconds".format(time.time() - test_start_time))

