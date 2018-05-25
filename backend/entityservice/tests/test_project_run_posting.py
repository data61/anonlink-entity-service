from entityservice.tests.config import url
from entityservice.tests.util import create_project_no_data, create_project_upload_fake_data, post_run, get_runs


# TODO: These two tests differ only in whether project has data in it
# or not; refactor with a fixture that gives different project types.
def test_posting_run_before_data_upload(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.95)
    runs = get_runs(requests, project)

    assert len(runs) == 1
    run = runs[0]
    assert 'run_id' in run
    assert 'time_added' in run
    assert 'state' in run
    assert run['state'] == 'created'


def test_posting_run_after_data_upload(requests):
    project, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    run_id = post_run(requests, project, 0.95)
    runs = get_runs(requests, project)

    assert len(runs) == 1
    for run in runs:
        assert 'run_id' in run
        assert 'time_added' in run
        assert 'state' in run
