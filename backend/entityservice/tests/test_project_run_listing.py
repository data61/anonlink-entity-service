from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data, get_runs, post_run


def test_empty_list_run(requests, example_mapping_projects):
    project = example_mapping_projects
    r = get_runs(requests, project)
    assert r == []


def test_list_run_noauth(requests, example_mapping_projects):
    project = example_mapping_projects
    r = requests.get(url + '/projects/{}/runs'.format(project['project_id']))
    assert r.status_code == 400


def test_list_run_invalid_auth(requests, example_mapping_projects):
    project = example_mapping_projects
    _ = get_runs(requests, project, 'invalid', expected_status = 403)


def test_list_run_after_posting_runs(requests):
    project = create_project_no_data(requests)

    for i in range(1, 11):
        run_id = post_run(requests, project, 0.95)
        # Check run listing has changed
        runs = get_runs(requests, project)
        assert len(runs) == i
