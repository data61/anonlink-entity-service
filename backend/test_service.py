import json
from base64 import b64encode, b64decode

import math
import requests
import time
from anonlink import randomnames, entitymatch

from serialization import *

# When running behind ngnix
url = "http://localhost:8851/api/v1"

# When running directly
#url = "http://localhost:8851"

def simpletest(dataset_size=1000):
    """
    Uses the NameList data and schema
    """
    print("Connecting to server.")
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
    new_map_response = requests.post(url + '/mappings', json={'schema': schema}).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    print("New mapping request created with id: ", id)
    assert new_map_response['ready'] == False

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

    print("Waiting some arbitrary amount of time...")
    time.sleep(3)

    print("Retrieving mapping")
    # TODO add auth token for this call?
    response = requests.get(url + '/mappings/{}'.format(id), json={'token': new_map_response['result_token']})

    print(response.status_code)
    assert response.status_code == 200
    mapping_result = response.json()
    print(mapping_result)


def create_test_data(entities, crossover=0.8, save_raw=True):
    """
    Uses the NameList data and schema and creates
    local files for raw data and clk data:

    - e1_NUM_raw.csv
    - e1_NUM.json
    - e2_NUM_raw.csv
    - e2_NUM.json

    :param bool save_raw: Set to False to skip saving raw files
    """
    print("Generating random test data for {} individuals".format(entities))

    from timeit import default_timer as timer

    t0 = timer()

    nl = randomnames.NameList(entities * 2)
    s1, s2 = nl.generate_subsets(entities, crossover)
    t1 = timer()
    print("generated data in {:.3f} s".format(t1-t0))

    def save_subset_data(s, f):
        print(",".join(nl.schema), file=f)
        for entity in s:
            print(",".join(map(str, entity)), file=f)

    def save_filter_data(filters, f):
        print("Serializing filters")
        serialized_filters = serialize_filters(filters)

        json.dump(serialized_filters, f)


    keys = ('something', 'secret')

    if save_raw:
        with open("data/e1_{}_raw.csv".format(entities), "w") as f:
            save_subset_data(s1, f)

        with open("data/e2_{}_raw.csv".format(entities), "w") as f:
            save_subset_data(s2, f)
    t2 = timer()
    print("Saved raw data in {:.3f} s".format(t2-t1))
    print("Locally hashing identity data to create bloom filters")

    # Save serialized filters
    with open("data/e1_{}.json".format(entities), 'w') as f1:
        save_filter_data(entitymatch.calculate_bloom_filters(s1, nl.schema, keys), f1)

    with open("data/e2_{}.json".format(entities), 'w') as f2:
        save_filter_data(entitymatch.calculate_bloom_filters(s2, nl.schema, keys), f2)

    t3 = timer()
    print("Hashed and serialized data in {:.3f} s".format(t3-t2))


if __name__ == "__main__":

    #create_test_data(1000000)

    # simpletest(200)
    #
    # simpletest(500)
    #
    simpletest(10000)
    #
    # simpletest(100000)
