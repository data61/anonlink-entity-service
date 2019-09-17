from entityservice.tests.util import post_run, delete_project, create_project_upload_fake_data, delete_run, \
    get_project_description, get_run, wait_for_run_completion
import pytest


def test_delete_project_after_creating_run_with_clks(requests, result_type_number_parties):
    project, run_id = _create_data_linkage_run(requests, result_type_number_parties)
    delete_project(requests, project)
    with pytest.raises(AssertionError):
        get_project_description(requests, project)


def test_delete_runs_after_creating_run_with_clks(requests, result_type_number_parties):
    project, run_id = _create_data_linkage_run(requests, result_type_number_parties)
    delete_run(requests, project['project_id'], run_id, project['result_token'])
    _checks_after_run_deleted(requests, project, run_id)


def test_delete_runs_after_completed_run(requests, result_type_number_parties):
    project, run_id = _create_data_linkage_run(requests, result_type_number_parties)
    result_token = project['result_token']
    wait_for_run_completion(requests, project, run_id, result_token, timeout=30)
    delete_run(requests, project['project_id'], run_id, result_token)
    _checks_after_run_deleted(requests, project, run_id)
    delete_run(requests, project['project_id'], run_id, result_token)
    _checks_after_run_deleted(requests, project, run_id)


def _create_data_linkage_run(requests, result_type_number_parties):
    result_type, number_parties = result_type_number_parties
    project, _ = create_project_upload_fake_data(
        requests, [100] * number_parties, overlap=0.5, result_type=result_type)
    run_id = post_run(requests, project, 1.0)
    return project, run_id


def _checks_after_run_deleted(requests, project, run_id):
    # This should still work
    get_project_description(requests, project)
    with pytest.raises(AssertionError):
        get_run(requests, project, run_id, expected_status=401)
