import json
from base64 import b64encode, b64decode
import requests
import time
from anonlink import randomnames, entitymatch

from serialization import *


#url = "http://localhost:8851/api/v1"
url = "http://localhost:8851"

def simpletest(dataset_size=1000):
    """
    Uses the NameList data and schema
    """
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
    new_map_response = requests.post(url + '/mappings', data={}).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    print("New mapping request created with id: ", id)
    assert new_map_response['ready'] == False

    print("Checking status before posting any data...")
    r = requests.get(url + '/mappings/{}'.format(id))
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
    response = requests.get(url + '/mappings/{}'.format(id))

    print(response.status_code)
    assert response.status_code == 200
    mapping_result = response.json()
    print(mapping_result)


def serialization_test():
    """
    Uses the NameList data and schema
    """
    print("Generating local address data")
    nl = randomnames.NameList(100000)
    s1, s2 = nl.generate_subsets(10000, 0.8)

    print("Locally hashing identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = entitymatch.calculate_bloom_filters(s1, nl.schema, keys)

    party1_filters = serialize_filters(filters1)


    data = json.dumps(party1_filters)

    print("Request size is: {}".format(len(data)))
    print(data, file=open("testout.txt", 'w'))



if __name__ == "__main__":
    #serialization_test()

    simpletest(200)

    simpletest(500)

    #simpletest(10000)

    #simpletest(100000)
