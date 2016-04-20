import os
import json
from base64 import b64encode, b64decode

import math
import requests
import time
from anonlink import randomnames, entitymatch

from serialization import *

"""
The URL to test can be overridden with the environment variable
ENTITY_SERVICE_URL

# When running behind ngnix
url = "http://localhost:8851/api/v1"

# When running directly
url = "http://localhost:8851"
"""
url = os.environ.get("ENTITY_SERVICE_URL", "http://localhost:8851/api/v1")



def simpletest(dataset_size=1000):
    """
    Uses the NameList data and schema
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

    print("Checking status with invalid token")
    r = requests.get(url + '/mappings/{}'.format(id), json={'token': 'invalid'})
    print(r.status_code, r.json())
    assert r.status_code == 403

    print("Checking status with valid token")
    r = requests.get(url + '/mappings/{}'.format(id), json={'token': new_map_response['result_token']})
    print(r.status_code, r.json())
    assert r.status_code == 503

    print("Adding first party's filter data")

    party1_data = {
        'token': new_map_response['update_tokens'][0],
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id), json=party1_data)
    # status code should be 201 if a resource was created
    assert resp1.status_code == 201

    print(resp1.json())

    print("Adding second party's data")
    party2_data = {
        'token': new_map_response['update_tokens'][1],
        'clks': party2_filters
    }

    resp2 = requests.put(url + '/mappings/{}'.format(id), json=party2_data)

    assert resp2.status_code == 201

    print("Going to sleep to give the server some processing time...")
    time.sleep(3)

    def retrieve_result():
        print("Retrieving mapping")
        response = requests.get(url + '/mappings/{}'.format(id), json={'token': new_map_response['result_token']})
        print(response.status_code)
        return response

    response = retrieve_result()
    while not response.status_code == 200:
        snooze = 10*dataset_size/10000
        print("Sleeping for another {} seconds".format(snooze))
        time.sleep(snooze)
        response = retrieve_result()

    assert response.status_code == 200

    mapping_result = response.json()
    print(mapping_result)



if __name__ == "__main__":

    size = int(os.environ.get("ENTITY_SERVICE_TEST_SIZE", "10000"))
    simpletest(size)
