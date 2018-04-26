import random
import time
import unittest

import anonlink
from clkhash import randomnames
from anonlink.util import generate_clks

import math

import base64

from entityservice.tests.config import url, logger, rate_limit_delay, initial_delay


def serialize_bitarray(ba):
    """ Serialize a bitarray (bloomfilter)

    """
    return base64.encodebytes(ba.tobytes()).decode('utf8')


def serialize_filters(filters):
    """Serialize filters as clients are required to."""
    return [
        serialize_bitarray(f[0]) for f in filters
    ]


def generate_serialized_clks(size):
    clks = generate_clks(size)
    return [serialize_bitarray(clk) for clk,_ ,_ in clks]


def generate_overlapping_clk_data(dataset_sizes, overlap=0.9):

    datasets = []
    for size in dataset_sizes:
        datasets.append(generate_serialized_clks(size))

    # TODO enforce overlap
    overlap_to = math.floor(dataset_sizes[0]*overlap)
    for ds in datasets[1:]:
        ds[:overlap_to] = datasets[0][:overlap_to]
        random.shuffle(ds)

    return datasets


class EntityServiceTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        time.sleep(initial_delay)

    def setUp(self):
        self.url = url
        self.log = logger

    def tearDown(self):
        # Small sleep to avoid hitting rate limits while testing
        time.sleep(rate_limit_delay)


def get_project_description(requests, new_project_data):
    project_description_response = requests.get(url + '/projects/{}'.format(new_project_data['project_id']),
                            headers={'Authorization': new_project_data['result_token']})

    assert project_description_response.status_code == 200
    return project_description_response.json()


def create_project_no_data(requests):
    new_project_response = requests.post(url + '/projects',
                                     headers={'Authorization': 'invalid'},
                                     json={
                                         'schema': {},
                                         'result_type': 'mapping',
                                     })
    assert new_project_response.status_code == 201
    return new_project_response.json()


def create_project_upload_fake_data(requests, size):
    new_project_data = create_project_no_data(requests)

    d1, d2 = generate_overlapping_clk_data(size, overlap=0.75)
    r1 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][0]},
        json={
            'clks': d1
        }
    )
    r2 = requests.post(
        url + '/projects/{}/clks'.format(new_project_data['project_id']),
        headers={'Authorization': new_project_data['update_tokens'][1]},
        json={
            'clks': d2
        }
    )
    assert r1.status_code == 201
    assert r2.status_code == 201

    return new_project_data, r1.json(), r2.json()
