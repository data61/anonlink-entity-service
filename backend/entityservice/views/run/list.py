from flask import request, g
from structlog import get_logger

from entityservice import app, database as db
from entityservice.tasks import check_for_executable_runs
from entityservice.database import get_db, get_runs, update_run_mark_queued
from entityservice.models.run import Run
from entityservice.utils import safe_fail_request
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_results_token
from entityservice.views.serialization import RunList, RunDescription
from entityservice.tracing import serialize_span

logger = get_logger()


def get(project_id):
    log = logger.bind(pid=project_id)
    log.info("Listing runs for project: {}".format(project_id))

    authorize_run_listing(project_id)

    log.info("Authorized request to list runs")

    return RunList().dump(get_runs(get_db(), project_id))


def post(project_id, run):
    log = logger.bind(pid=project_id)
    log.debug("Processing request to add a new run", run=run)
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    run_model = Run.from_json(run, project_id)

    log.debug("Saving run")
    db_conn = db.get_db()
    run_model.save(db_conn)

    project_object = db.get_project(db_conn, project_id)
    parties_contributed = db.get_number_parties_uploaded(db_conn, project_id)
    log.debug("Expecting {} parties to upload data. Have received {}".format(
        project_object['parties'], parties_contributed
    ))
    if parties_contributed == project_object['parties']:
        log.info("Scheduling task to carry out all runs for project {} now".format(project_id))
        with db_conn:
            update_run_mark_queued(db_conn, run_model.run_id)
        span = g.flask_tracer.get_span()
        span.set_tag("run_id", run_model.run_id)
        span.set_tag("project_id", run_model.project_id)
        check_for_executable_runs.delay(project_id, serialize_span(span))
    else:
        log.info("Task queued but won't start until CLKs are all uploaded")
    return RunDescription().dump(run_model), 201


def authorize_run_listing(project_id):
    logger.info("Looking up project")
    # Check the project resource exists
    abort_if_project_doesnt_exist(project_id)
    if request.headers is None or 'Authorization' not in request.headers:
        safe_fail_request(401, message="Authentication token required")
    auth_header = request.headers.get('Authorization')
    logger.info("Checking credentials to list project runs")
    # Check the caller has a valid results token (analyst token)
    abort_if_invalid_results_token(project_id, auth_header)
    logger.info("Caller is allowed to list project runs")
