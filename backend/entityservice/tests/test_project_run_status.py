import datetime
import time
from requests import sessions
import iso8601

from entityservice.tests.config import url
from entityservice.tests.util import create_project_upload_fake_data, create_project_no_data
from entityservice.tests.util import has_progressed, post_run, get_run_status, is_run_status


def wait_while_not_running(request, timeout=30, interval=1):
    """
    waits for maximum 'timeout' seconds for this run to change its state to something other than 'queued' or 'created'.
    """
    start = datetime.datetime.now()
    while datetime.datetime.now() - start < datetime.timedelta(seconds=timeout):
        with sessions.Session() as session:
            response = session.send(request)
        if response.json().get('state') not in ('queued', 'created'):
            return response
        time.sleep(interval)
    raise TimeoutError('timeout reached while waiting for this run to un-queue...')


# TODO: This is practically the same as test_project_runs.py::test_run_larger()
def test_run_status_with_clks(requests):
    project, dp1, dp2 = create_project_upload_fake_data(requests, [1000, 1000])

    run_id = post_run(requests, project, 0.9)
    time_posted = datetime.datetime.now(tz=datetime.timezone.utc)

    r = requests.get(url + '/projects/{}/runs/{}/status'.format(
        project['project_id'],
        run_id
        ),
        headers={'Authorization': project['result_token']})
    r = wait_while_not_running(r.request)

    assert r.status_code == 200
    status = r.json()

    is_run_status(status)
    assert status['state'] in ('running', 'completed')

    dt = iso8601.parse_date(status['time_added'])

    assert time_posted - dt < datetime.timedelta(seconds=5)
    if status['state'] == 'running':
        original_status = status

        # Wait and see if the progress changes. Project should easily be complete
        time.sleep(5)
        status = get_run_status(requests, project, run_id)

        assert has_progressed(original_status, status)


def test_run_status_without_clks(requests):
    project = create_project_no_data(requests)

    run_id = post_run(requests, project, 0.9)
    status = get_run_status(requests, project, run_id)

    is_run_status(status)
    assert status['state'] == 'created'
