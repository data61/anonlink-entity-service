import requests

from entityservice.tests.config import url


def test_version(record_property):
    version_obj = requests.get(url + '/version').json()
    record_property('version', version_obj)

    assert 'python' in version_obj
    assert 'entityservice' in version_obj
    assert 'anonlink' in version_obj


def test_status(record_property):
    status = requests.get(url + '/status')
    assert status.status_code == 200, 'Server status was {}'.format(status.status_code)

    status_json = status.json()
    record_property("status", status_json)

    assert 'status' in status_json
    assert status_json['status'] == 'ok'
    assert 'rate' in status_json
    assert 'project_count' in status_json


def test_metrics(record_property):
    response = requests.get(url + '/metrics')
    assert response.status_code == 200, 'Server status was {}'.format(response.status_code)

    record_property("metrics", response.text)

    print(response.text)

