import pytest
from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, post_run, get_run
from entityservice.tests.conftest import example_mapping_projects


def test_run_description_missing_run(requests, example_mapping_projects):
    project = example_mapping_projects
    _ = get_run(requests, project, 'invalid', expected_status = 403)


def test_run_description(requests, example_mapping_projects):
    project = example_mapping_projects

    run_id = post_run(requests, project, 0.95)
    run = get_run(requests, project, run_id)

    assert 'run_id' in run
    assert 'notes' in run
    assert 'threshold' in run
