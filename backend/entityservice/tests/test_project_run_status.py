import datetime
import time

import iso8601

from entityservice.tests.util import has_progressed, post_run, get_run_status, wait_while_queued, is_run_status, \
    create_project_no_data


# TODO: This is practically the same as test_project_runs.py::test_run_larger()
def test_run_status_with_clks(requests, mapping_project):
    run_id = post_run(requests, mapping_project, 0.9)
    time_posted = datetime.datetime.now(tz=datetime.timezone.utc)
    status = wait_while_queued(requests, mapping_project, run_id)
    is_run_status(status)
    assert status['state'] in ('running', 'completed')

    dt = iso8601.parse_date(status['time_added'])

    assert time_posted - dt < datetime.timedelta(seconds=5)
    original_status = status

    # Wait and see if the progress changes. Project should easily be complete
    time.sleep(1)
    status = get_run_status(requests, mapping_project, run_id)

    assert has_progressed(original_status, status)


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)
    assert status['state'] == 'created'
