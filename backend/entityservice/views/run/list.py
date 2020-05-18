from flask import request, g
from structlog import get_logger

from entityservice import database as db
from entityservice.tasks import check_for_executable_runs
from entityservice.database import get_runs
from entityservice.models.run import Run
from entityservice.utils import safe_fail_request
from entityservice.views import bind_log_and_span
from entityservice.views.auth_checks import abort_if_project_doesnt_exist, abort_if_invalid_results_token, \
    abort_if_project_in_error_state
from entityservice.views.serialization import RunListItem, RunDescription
from entityservice.tracing import serialize_span

logger = get_logger()


def get(project_id):
    log, parent_span = bind_log_and_span(project_id)
    log.info("Listing runs for project")

    authorize_run_listing(project_id)

    log.info("Authorized request to list runs")
    with db.DBConn() as conn:
        runs = get_runs(conn, project_id)

    return RunListItem(many=True).dump(runs)


def post(project_id, run):
    log, span = bind_log_and_span(project_id)
    log.debug("Processing request to add a new run", run=run)
    # Check the resource exists
    abort_if_project_doesnt_exist(project_id)

    # Check the caller has a valid results token. Yes it should be renamed.
    abort_if_invalid_results_token(project_id, request.headers.get('Authorization'))

    abort_if_project_in_error_state(project_id)

    run_model = Run.from_json(run, project_id)

    log.debug("Saving run")

    with db.DBConn() as db_conn:
        run_model.save(db_conn)

    check_for_executable_runs.delay(project_id, serialize_span(span))
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
