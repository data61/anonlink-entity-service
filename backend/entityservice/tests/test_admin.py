import requests
from tests.util import EntityServiceTestBase


class TestAdmin(EntityServiceTestBase):

    def test_version(self):
        version_obj = requests.get(self.url + '/version').json()
        self.log.info(version_obj)
        self.assertIn('python', version_obj)
        self.assertIn('entityservice', version_obj)
        self.assertIn('anonlink', version_obj)

    def test_status(self):
        status = requests.get(self.url + '/status')
        self.log.debug("Server status:")
        self.assertEqual(status.status_code, 200, 'Server status was {}'.format(status.status_code))
        status_json = status.json()
        self.log.info(status_json)
        self.assertIn('status', status_json)
        self.assertEqual(status_json['status'], 'ok')
        self.assertIn('rate', status_json)
        self.assertIn('number_mappings', status_json)

