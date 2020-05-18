from e2etests.util import post_run, get_runs


def test_posting_run_before_data_upload(requests, project):
    run_id = post_run(requests, project, 0.95)
    runs = get_runs(requests, project)

    assert len(runs) == 1
    run = runs[0]
    assert 'run_id' in run
    assert 'time_added' in run
    assert 'state' in run
    assert run['state'] == 'created'


def test_posting_run_after_data_upload(requests, project):
    run_id = post_run(requests, project, 0.95)
    runs = get_runs(requests, project)

    assert len(runs) == 1
    for run in runs:
        assert 'run_id' in run
        assert run['run_id'] == run_id
        assert 'time_added' in run
        assert 'state' in run
