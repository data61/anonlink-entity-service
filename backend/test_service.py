import json
from base64 import b64encode, b64decode
import requests
from anonlink import randomnames, entitymatch

from serialization import *

url = "http://localhost:8888"



def simpletest():
    """
    Uses the NameList data and schema
    """
    print("Generating local address data")
    nl = randomnames.NameList(100)
    s1, s2 = nl.generate_subsets(10, 0.8)

    print("Locally hashing identity data to create bloom filters")
    keys = ('something', 'secret')
    filters1 = entitymatch.calculate_bloom_filters(s1, nl.schema, keys)
    filters2 = entitymatch.calculate_bloom_filters(s2, nl.schema, keys)

    party1_filters = serialize_filters(filters1)
    party2_filters = serialize_filters(filters2)

    print(requests.get(url + '/mappings').json())

    print('Create a new mapping request')
    new_map_response = requests.post(url + '/mappings', data={}).json()
    print(new_map_response)

    id = new_map_response['resource_id']
    print("New mapping request created with id: ", id)
    assert new_map_response['ready'] == False

    print("Getting request before posting any data...")
    assert requests.get(url + '/mappings/{}'.format(id)).status_code == 503

    print("Adding first party's data")
    party1_data = {
        'token': new_map_response['update_tokens'][0],
        'clks': party1_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id), json=party1_data)

    print(resp1.json())
    print("Adding second party's data")
    party2_data = {
        'token': new_map_response['update_tokens'][1],
        'clks': party2_filters
    }

    resp1 = requests.put(url + '/mappings/{}'.format(id), json=party2_data)

    print(resp1.json())

    print("Checking that mapping is ready")
    # TODO add auth token for this call?
    response = requests.get(url + '/mappings/{}'.format(id))

    print(response.status_code)
    mapping_result = response.json()

    print(mapping_result)



if __name__ == "__main__":
    simpletest()