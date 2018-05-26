import datetime
import time
from requests import sessions
import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data
from entityservice.tests.util import has_progressed, post_run, get_run_status, wait_while_queued


# TODO: This is practically the same as test_project_runs.py::test_run_larger()
def test_run_status_with_clks(requests, mapping_project):
    run_id = post_run(requests, mapping_project, 0.9)
    time_posted = datetime.datetime.now(tz=datetime.timezone.utc)
    status = wait_while_queued(requests, mapping_project, run_id)

    assert 'state' in status
    assert 'message' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    if status['state'] == 'running':
        assert 'time_started' in status
        assert 'progress' in status
    elif status['state'] == 'completed':
        assert 'time_started' in status
        assert 'time_completed' in status

    dt = iso8601.parse_date(status['time_added'])

    assert time_posted - dt < datetime.timedelta(seconds=5)
    original_status = status

    # Wait and see if the progress changes. This assumes a comparison rate of 10 M/s
    time.sleep(2 + mapping_project['size'][0] * mapping_project['size'][1]/10_000_000)
    status = get_run_status(requests, mapping_project, run_id)

    assert has_progressed(original_status, status)


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    assert 'state' in status
    assert 'message' in status
    assert 'time_added' in status
    assert status['state'] == 'queued'
