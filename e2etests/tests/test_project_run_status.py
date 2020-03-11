
from e2etests.util import post_run, get_run_status, is_run_status, \
    create_project_no_data


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)
    assert status['state'] == 'created'
