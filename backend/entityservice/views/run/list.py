from flask import request

from entityservice import app, database as db
from entityservice.async_worker import check_for_executable_runs
from entityservice.database import get_db, get_runs
from entityservice.models.run import Run
from entityservice.utils import safe_fail_request
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_results_token
from entityservice.views.serialization import RunList, RunDescription


def get(project_id):
    app.logger.info("Listing runs for project: {}".format(project_id))

    authorize_run_listing(project_id)

    app.logger.info("Authorized request to list runs")

    return RunList().dump(get_runs(get_db(), project_id))


def post(project_id, run):

    app.logger.debug("Processing request to add a new run")
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    run_model = Run.from_json(run, project_id)

    app.logger.debug("Saving run")
    db_conn = db.get_db()
    run_model.save(db_conn)

    project_object = db.get_project(db_conn, project_id)
    parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)

    if parties_contributed == project_object['parties']:
        app.logger.info("Scheduling task to carry out all runs for this project now")
        check_for_executable_runs.delay(project_id)
    else:
        app.logger.info("Task queued but won't start until CLKs are all uploaded")
    return RunDescription().dump(run_model), 201


def authorize_run_listing(project_id):
    app.logger.info("Looking up project")
    # Check the project resource exists
    abort_if_project_doesnt_exist(project_id)
    if request.headers is None or 'Authorization' not in request.headers:
        safe_fail_request(401, message="Authentication token required")
    auth_header = request.headers.get('Authorization')
    app.logger.info("Checking credentials to list project runs")
    # Check the caller has a valid results token (analyst token)
    abort_if_invalid_results_token(project_id, auth_header)
    app.logger.info("Caller is allowed to list project runs")
