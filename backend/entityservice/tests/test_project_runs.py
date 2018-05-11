import datetime
import time

import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, has_progressed, post_run, get_run_status


def test_run_larger(requests):
    project, dp1, dp2 = create_project_upload_fake_data(requests, [100000, 10000])

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    assert 'state' in status
    assert 'message' in status
    assert 'time_added' in status
    assert status['state'] in {'queued', 'running', 'completed'}

    original_status = status

    dt = iso8601.parse_date(status['time_added'])
    assert datetime.datetime.now(tz=datetime.timezone.utc) - dt < datetime.timedelta(seconds=5)

    # Wait and see if the progress changes
    time.sleep(30)
    status = get_run_status(requests, project, run_id)
    assert has_progressed(original_status, status)

