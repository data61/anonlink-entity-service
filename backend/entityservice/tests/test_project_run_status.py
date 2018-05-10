import datetime
import time

import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data, post_run, get_run_status


# TODO: This is practically the same as test_project_runs.py::test_run_larger()
def test_run_status_with_clks(requests):
    project, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    run_id = post_run(requests, project, 0.9)
    time_posted = datetime.datetime.now(tz=datetime.timezone.utc)
    status = get_run_status(requests, project, run_id)

    assert 'state' in status
    assert 'message' in status
    assert 'progress' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    if status['state'] == 'running':
        assert 'time_started' in status
    elif status['state'] == 'completed':
        assert 'time_started' in status
        assert 'time_completed' in status

    dt = iso8601.parse_date(status['time_added'])

    assert time_posted - dt < datetime.timedelta(seconds=5)
    original_progress = status['progress']['progress']

    # Wait and see if the progress changes. Project should easily be complete
    time.sleep(5)
    status = get_run_status(requests, project, run_id)
    if original_progress != 1.0:
        assert status['progress']['progress'] > original_progress

    assert status['state'] == 'completed'
    assert 'time_started' in status
    assert 'time_completed' in status


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    assert 'state' in status
    assert 'message' in status
    assert 'progress' in status
    assert 'time_added' in status
    assert status['state'] == 'queued'
