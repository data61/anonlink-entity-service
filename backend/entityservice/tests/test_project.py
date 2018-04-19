import time
import pytest
import requests

from entityservice.tests.config import url
from entityservice.tests.util import generate_serialized_clks, generate_overlapping_clk_data

#
# class ProjectTestBase(EntityServiceTestBase):
#
#     def setUp(self):
#         super().setUp()
#         self.projects = []
#
#     def tearDown(self):
#         for project_id in self.projects:
#             self.log.debug("Removing project created for testing: {}".format(project_id))
#             self.delete_project_from_server(project_id)
#         super().tearDown()
#
#     def delete_project_from_server(self, pid):
#         requests.delete(self.url + 'projects/{}'.format(pid))
#


def test_create_project():
    project_creation_response = requests.post(url + '/projects', json={
        'schema': {},
        'result_type': 'mapping',
        'threshold': 0.95
    }).json()

    print(project_creation_response)

    # clean up?
    #projects.append(project_creation_response['project_id'])

def test_create_then_delete():
    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        'result_type': 'mapping',
        'threshold': 0.95
    }).json()

    print(new_project_response)
    requests.delete(url + 'projects/{}'.format(new_project_response['project_id']))


def test_create_then_list():
    original_project_list_respose = requests.get(url + '/projects').json()
    original_project_ids = [p['project_id'] for p in original_project_list_respose]

    new_project_response = requests.post(url + '/projects', json={
        'schema': {},
        'result_type': 'mapping',
        'threshold': 0.95
    }).json()

    assert new_project_response['project_id'] not in original_project_list_respose

    project_list_response = requests.get(url + '/projects').json()
    new_project_ids = [p['project_id'] for p in project_list_response]

    assert new_project_response['project_id'] in new_project_ids

    # def test_project_status_noauth(self):
    #     new_mapping = requests.post(self.url + '/projects', json={
    #         'schema': {},
    #         'result_type': 'mapping',
    #         'threshold': 0.95
    #     }).json()
    #
    #     self.log.info("Checking mapping status without authentication token")
    #     r = requests.get(self.url + '/mappings/{}'.format(new_mapping['resource_id']))
    #     self.assertEqual(r.status_code, 401)
    #
    #     self.projects.append(new_mapping['resource_id'])
    #
    # def test_mapping_status_invalid_auth(self):
    #     new_map_response = requests.post(self.url + '/mappings',
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     r = requests.get(self.url + '/mappings/{}'.format(new_map_response['resource_id']),
    #                      headers={'Authorization': 'invalid'},
    #                      )
    #     self.assertEqual(r.status_code, 403)
    #     self.projects.append(new_map_response['resource_id'])
    #
    # def test_mapping_status_invalid_mapping_id_fake_auth(self):
    #     r = requests.get(self.url + '/mappings/{}'.format('fakeid'),
    #                      headers={'Authorization': 'invalid'})
    #     self.assertEqual(r.status_code, 403)
    #
    # def test_mapping_status_invalid_mapping_id_valid_auth(self):
    #     new_map_response = requests.post(self.url + '/mappings',
    #                                      headers={'Authorization': 'invalid'},
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     r = requests.get(self.url + '/mappings/{}'.format('fakeid'),
    #                      headers={'Authorization': new_map_response['result_token']})
    #     self.assertEqual(r.status_code, 403)
    #     self.projects.append(new_map_response['resource_id'])
    #
    # def test_mapping_status_no_data_uploaded(self):
    #     new_map = requests.post(self.url + '/mappings',
    #                                      headers={'Authorization': 'invalid'},
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     r = requests.get(self.url + '/mappings/{}'.format(new_map['resource_id']),
    #                      headers={'Authorization': new_map['result_token']})
    #     self.assertEqual(r.status_code, 503)
    #     update = r.json()
    #
    #     self.assertIn('progress', update)
    #     self.assertIn('current', update)
    #     self.assertIn('elapsed', update)
    #     self.assertIn('message', update)
    #     self.assertIn('total', update)
    #
    #     self.projects.append(new_map['resource_id'])
    #
    # def test_mapping_single_party_data_uploaded(self):
    #     new_map = requests.post(self.url + '/mappings',
    #                                      headers={'Authorization': 'invalid'},
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     r = requests.put(
    #         self.url + '/mappings/{}'.format(new_map['resource_id']),
    #         headers={'Authorization': new_map['update_tokens'][0]},
    #         json={
    #             'clks': generate_serialized_clks(100)
    #         }
    #     )
    #     self.assertEqual(r.status_code, 201)
    #     upload_response = r.json()
    #     self.assertIn('receipt-token', upload_response)
    #     self.projects.append(new_map['resource_id'])
    #
    #
    # def test_mapping_single_party_empty_data_upload(self):
    #     new_map = requests.post(self.url + '/mappings',
    #                                      headers={'Authorization': 'invalid'},
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     self.log.info("Testing uploading 0 clks")
    #     r = requests.put(
    #         self.url + '/mappings/{}'.format(new_map['resource_id']),
    #         headers={'Authorization': new_map['update_tokens'][0]},
    #         json={
    #             'clks': []
    #         }
    #     )
    #     self.assertEqual(r.status_code, 400)
    #
    #
    # def test_mapping_2_party_data_uploaded(self):
    #     new_map = requests.post(self.url + '/mappings',
    #                                      headers={'Authorization': 'invalid'},
    #                                      json={
    #                                          'schema': TestProjectTest.schema,
    #                                          'result_type': 'mapping',
    #                                          'threshold': 0.8
    #                                      }).json()
    #     self.projects.append(new_map['resource_id'])
    #     d1, d2 = generate_overlapping_clk_data([100, 100], overlap=0.75)
    #     r1 = requests.put(
    #         self.url + '/mappings/{}'.format(new_map['resource_id']),
    #         headers={'Authorization': new_map['update_tokens'][0]},
    #         json={
    #             'clks': d1
    #         }
    #     )
    #     r2 = requests.put(
    #         self.url + '/mappings/{}'.format(new_map['resource_id']),
    #         headers={'Authorization': new_map['update_tokens'][1]},
    #         json={
    #             'clks': d2
    #         }
    #     )
    #     self.assertEqual(r1.status_code, 201)
    #     self.assertEqual(r2.status_code, 201)
    #
    #     time.sleep(5)
    #     response = requests.get(self.url + '/mappings/{}'.format(new_map['resource_id']),
    #                             headers={'Authorization': new_map['result_token']})
    #
    #     mapping_result = response.json()['mapping']
    #     self.assertGreater(len(mapping_result), 70)
    #     self.assertLess(len(mapping_result), 80)
