import pytest
from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, post_run, get_run


def test_run_description_missing_run(requests, mapping_project):
    _ = get_run(requests, mapping_project, 'invalid', expected_status = 403)


def test_run_description(requests, mapping_project):
    run_id = post_run(requests, mapping_project, 0.95)
    run = get_run(requests, mapping_project, run_id)

    assert 'run_id' in run
    assert 'notes' in run
    assert 'threshold' in run
