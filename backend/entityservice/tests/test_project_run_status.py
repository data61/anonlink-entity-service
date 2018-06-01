import datetime
import time

import iso8601

from entityservice.tests.util import has_progressed, post_run, get_run_status, wait_while_queued, is_run_status, \
    create_project_no_data, ensure_run_progressing


def test_run_status_with_clks(requests, mapping_project):
    run_id = post_run(requests, mapping_project, 0.9)
    size = mapping_project['size']
    ensure_run_progressing(requests, mapping_project, size)


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)
    assert status['state'] == 'created'
