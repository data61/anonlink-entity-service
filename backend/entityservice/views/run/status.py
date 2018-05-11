from flask import request

from entityservice import app, database as db, cache as cache
from entityservice.database import get_db
from entityservice.views.auth_checks import abort_if_run_doesnt_exist, abort_if_invalid_results_token
from entityservice.views.serialization import completed, running, RunStatus


def get(project_id, run_id):
    app.logger.info("request run status")
    # Check the project and run resources exist
    abort_if_run_doesnt_exist(project_id, run_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    app.logger.info("request for run status authorized")
    dbinstance = get_db()
    is_ready, state = db.check_run_ready(dbinstance, run_id)

    # return compute time elapsed and number of comparisons here
    times = db.get_run_times(dbinstance, run_id)

    status = {
        "state": state,
        "time_added": times['time_added'],
        "message": "Hello World"
    }

    if state == 'completed':
        status["time_started"] = times['time_started']
        status["time_completed"] = times['time_completed']
        return completed().dump(status)

    if state == 'running':
        comparisons = cache.get_progress(run_id)
        total_comparisons = db.get_total_comparisons_for_project(dbinstance, project_id)

        progress = {
            'total': total_comparisons,
            'current': comparisons,
            'progress': (comparisons / total_comparisons) if total_comparisons is not 'NA' else 0.0
        }
        status["time_started"] = times['time_started']
        status["progress"] = progress
        return running().dump(status)

    return RunStatus().dump(status)
