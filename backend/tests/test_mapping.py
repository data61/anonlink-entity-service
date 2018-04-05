import requests
import time

from tests.util import generate_serialized_clks, generate_overlapping_clk_data, EntityServiceTestBase


class MappingTestsBase(EntityServiceTestBase):

    def setUp(self):
        super().setUp()
        self.mappings = []

    def tearDown(self):
        for mid in self.mappings:
            self.log.debug("Removing test mapping: {}".format(mid))
            self.delete_mapping_from_server(mid)
        super().tearDown()

    def delete_mapping_from_server(self, mid):
        r = requests.delete(self.url + 'mappings/{}'.format(mid))


class TestMappingTests(MappingTestsBase):
    schema = [
        {"identifier": "INDEX", "weight": 0, "notes": ""},
        {"identifier": "NAME freetext", "weight": 1, "notes": "max length set to 128"},
        {"identifier": "DOB YYYY/MM/DD", "weight": 1, "notes": ""},
        {"identifier": "GENDER M or F", "weight": 1, "notes": ""}
    ]

    def test_create_mapping(self):
        new_map_response = requests.post(self.url + '/mappings', json={
            'schema': TestMappingTests.schema,
            'result_type': 'mapping',
            'threshold': 0.8
        }).json()

        self.log.debug(new_map_response)
        self.mappings.append(new_map_response['resource_id'])

    def test_create_then_delete_mapping(self):
        new_map_response = requests.post(self.url + '/mappings', json={
            'schema': TestMappingTests.schema,
            'result_type': 'mapping',
            'threshold': 0.8
        }).json()

        self.log.debug(new_map_response)
        r = requests.delete(self.url + 'mappings/{}'.format(new_map_response['resource_id']))

    def test_mapping_status_noauth(self):
        new_mapping = requests.post(self.url + '/mappings', json={
            'schema': TestMappingTests.schema,
            'result_type': 'mapping',
            'threshold': 0.8
        }).json()
        self.log.info("Checking mapping status without authentication token")
        r = requests.get(self.url + '/mappings/{}'.format(new_mapping['resource_id']))
        self.assertEqual(r.status_code, 401)

        self.mappings.append(new_mapping['resource_id'])

    def test_mapping_status_invalid_auth(self):
        new_map_response = requests.post(self.url + '/mappings',
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        r = requests.get(self.url + '/mappings/{}'.format(new_map_response['resource_id']),
                         headers={'Authorization': 'invalid'},
                         )
        self.assertEqual(r.status_code, 403)
        self.mappings.append(new_map_response['resource_id'])

    def test_mapping_status_invalid_mapping_id_fake_auth(self):
        r = requests.get(self.url + '/mappings/{}'.format('fakeid'),
                         headers={'Authorization': 'invalid'})
        self.assertEqual(r.status_code, 403)

    def test_mapping_status_invalid_mapping_id_valid_auth(self):
        new_map_response = requests.post(self.url + '/mappings',
                                         headers={'Authorization': 'invalid'},
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        r = requests.get(self.url + '/mappings/{}'.format('fakeid'),
                         headers={'Authorization': new_map_response['result_token']})
        self.assertEqual(r.status_code, 403)
        self.mappings.append(new_map_response['resource_id'])

    def test_mapping_status_no_data_uploaded(self):
        new_map = requests.post(self.url + '/mappings',
                                         headers={'Authorization': 'invalid'},
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        r = requests.get(self.url + '/mappings/{}'.format(new_map['resource_id']),
                         headers={'Authorization': new_map['result_token']})
        self.assertEqual(r.status_code, 503)
        update = r.json()

        self.assertIn('progress', update)
        self.assertIn('current', update)
        self.assertIn('elapsed', update)
        self.assertIn('message', update)
        self.assertIn('total', update)

        self.mappings.append(new_map['resource_id'])

    def test_mapping_single_party_data_uploaded(self):
        new_map = requests.post(self.url + '/mappings',
                                         headers={'Authorization': 'invalid'},
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        r = requests.put(
            self.url + '/mappings/{}'.format(new_map['resource_id']),
            headers={'Authorization': new_map['update_tokens'][0]},
            json={
                'clks': generate_serialized_clks(100)
            }
        )
        self.assertEqual(r.status_code, 201)
        upload_response = r.json()
        self.assertIn('receipt-token', upload_response)
        self.mappings.append(new_map['resource_id'])


    def test_mapping_single_party_empty_data_upload(self):
        new_map = requests.post(self.url + '/mappings',
                                         headers={'Authorization': 'invalid'},
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        self.log.info("Testing uploading 0 clks")
        r = requests.put(
            self.url + '/mappings/{}'.format(new_map['resource_id']),
            headers={'Authorization': new_map['update_tokens'][0]},
            json={
                'clks': []
            }
        )
        self.assertEqual(r.status_code, 400)


    def test_mapping_2_party_data_uploaded(self):
        new_map = requests.post(self.url + '/mappings',
                                         headers={'Authorization': 'invalid'},
                                         json={
                                             'schema': TestMappingTests.schema,
                                             'result_type': 'mapping',
                                             'threshold': 0.8
                                         }).json()
        self.mappings.append(new_map['resource_id'])
        d1, d2 = generate_overlapping_clk_data([100, 100], overlap=0.75)
        r1 = requests.put(
            self.url + '/mappings/{}'.format(new_map['resource_id']),
            headers={'Authorization': new_map['update_tokens'][0]},
            json={
                'clks': d1
            }
        )
        r2 = requests.put(
            self.url + '/mappings/{}'.format(new_map['resource_id']),
            headers={'Authorization': new_map['update_tokens'][1]},
            json={
                'clks': d2
            }
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)

        time.sleep(5)
        response = requests.get(self.url + '/mappings/{}'.format(new_map['resource_id']),
                                headers={'Authorization': new_map['result_token']})

        mapping_result = response.json()['mapping']
        self.assertGreater(len(mapping_result), 70)
        self.assertLess(len(mapping_result), 80)
